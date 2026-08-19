"""Workspace API-key management and authentication."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api_keys.models import ApiKey
from app.api_keys.principal import ApiKeyPrincipal
from app.api_keys.repository import ApiKeyRepository
from app.api_keys.scopes import DEFAULT_SCOPES, normalize_scopes
from app.api_keys.security import (
    display_prefix,
    generate_api_key_secret,
    hash_api_key,
    hashes_equal,
    last_four,
    parse_presented_api_key,
    reject_invalid_api_key,
)
from app.audit import AuditAction, AuditEntityType, record_audit
from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace, WorkspaceKind, WorkspaceStatus
from app.workspaces.repository import WorkspaceRepository


@dataclass(slots=True, frozen=True)
class CreatedApiKey:
    row: ApiKey
    plaintext: str = field(repr=False)


class ApiKeyService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.keys = ApiKeyRepository(db)
        self.workspaces = WorkspaceRepository(db)

    def list_keys(self, workspace_id: uuid.UUID) -> list[ApiKey]:
        return self.keys.list_for_workspace(workspace_id)

    def create_key(
        self,
        *,
        workspace: Workspace,
        actor_id: uuid.UUID,
        name: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> CreatedApiKey:
        self._require_tenant_workspace(workspace)
        if workspace.status != WorkspaceStatus.ACTIVE.value:
            raise AppError(
                ErrorCategory.WORKSPACE_ACCESS_DENIED,
                "Workspace is not active.",
                details={"status": workspace.status},
            )

        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > 100:
            raise AppError(
                ErrorCategory.VALIDATION,
                "API key name is required (max 100 characters).",
            )

        normalized_scopes = normalize_scopes(scopes)
        expiry = self._validate_expiry(expires_at)

        plaintext, row = self._build_key_row(
            workspace_id=workspace.id,
            name=clean_name,
            scopes=normalized_scopes,
            created_by=actor_id,
            expires_at=expiry,
        )
        try:
            self.keys.create(row)
            record_audit(
                self.db,
                action=AuditAction.API_KEY_CREATED,
                entity_type=AuditEntityType.API_KEY,
                entity_id=row.id,
                workspace_id=workspace.id,
                actor_user_id=actor_id,
                metadata={"prefix": row.key_prefix, "scopes": normalized_scopes},
                allowlist=frozenset({"prefix", "scopes"}),
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # Unique hash collision is vanishingly rare; retry once with a new secret.
            plaintext, row = self._build_key_row(
                workspace_id=workspace.id,
                name=clean_name,
                scopes=normalized_scopes,
                created_by=actor_id,
                expires_at=expiry,
            )
            try:
                self.keys.create(row)
                record_audit(
                    self.db,
                    action=AuditAction.API_KEY_CREATED,
                    entity_type=AuditEntityType.API_KEY,
                    entity_id=row.id,
                    workspace_id=workspace.id,
                    actor_user_id=actor_id,
                    metadata={"prefix": row.key_prefix, "scopes": normalized_scopes},
                    allowlist=frozenset({"prefix", "scopes"}),
                )
                self.db.commit()
            except IntegrityError as exc:
                self.db.rollback()
                raise AppError(
                    ErrorCategory.CONFLICT,
                    "Unable to create API key. Please retry.",
                ) from exc

        security_log(
            "api_key.created",
            api_key_id=str(row.id),
            workspace_id=str(workspace.id),
            user_id=str(actor_id),
            prefix=row.key_prefix,
            scopes=normalized_scopes,
        )
        return CreatedApiKey(row=row, plaintext=plaintext)

    def revoke_key(
        self,
        *,
        workspace_id: uuid.UUID,
        api_key_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> ApiKey:
        row = self.keys.get_by_id_for_workspace(workspace_id, api_key_id)
        if row is None:
            raise AppError(ErrorCategory.API_KEY_NOT_FOUND, "API key not found.")

        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            record_audit(
                self.db,
                action=AuditAction.API_KEY_REVOKED,
                entity_type=AuditEntityType.API_KEY,
                entity_id=row.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={"prefix": row.key_prefix},
                allowlist=frozenset({"prefix"}),
            )
            self.db.commit()
            security_log(
                "api_key.revoked",
                api_key_id=str(row.id),
                workspace_id=str(workspace_id),
                user_id=str(actor_id),
                prefix=row.key_prefix,
            )
        return row

    def authenticate(self, presented_secret: str) -> ApiKeyPrincipal:
        secret = parse_presented_api_key(presented_secret)
        digest = hash_api_key(secret, settings=self.settings)
        row = self.keys.get_by_secret_hash(digest)
        if row is None or not hashes_equal(row.secret_hash, digest):
            security_log("api_key.auth_failed", reason="invalid")
            reject_invalid_api_key()

        if row.revoked_at is not None:
            security_log(
                "api_key.auth_failed",
                reason="revoked",
                api_key_id=str(row.id),
                workspace_id=str(row.workspace_id),
            )
            reject_invalid_api_key()

        if row.expires_at is not None:
            expiry = row.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                security_log(
                    "api_key.auth_failed",
                    reason="expired",
                    api_key_id=str(row.id),
                    workspace_id=str(row.workspace_id),
                )
                reject_invalid_api_key()

        workspace = self.workspaces.get_by_id(row.workspace_id)
        if workspace is None:
            security_log(
                "api_key.auth_failed",
                reason="workspace_missing",
                api_key_id=str(row.id),
                workspace_id=str(row.workspace_id),
            )
            reject_invalid_api_key()

        if workspace.kind != WorkspaceKind.TENANT.value:
            security_log(
                "api_key.auth_failed",
                reason="workspace_not_tenant",
                api_key_id=str(row.id),
                workspace_id=str(workspace.id),
            )
            reject_invalid_api_key()

        if workspace.status != WorkspaceStatus.ACTIVE.value:
            security_log(
                "api_key.auth_failed",
                reason="workspace_inactive",
                api_key_id=str(row.id),
                workspace_id=str(workspace.id),
                status=workspace.status,
            )
            raise AppError(
                ErrorCategory.WORKSPACE_ACCESS_DENIED,
                "Workspace is not active.",
                details={"status": workspace.status},
            )

        scopes = tuple(str(s) for s in (row.scopes or list(DEFAULT_SCOPES)))
        principal = ApiKeyPrincipal(
            api_key_id=row.id,
            workspace_id=workspace.id,
            scopes=scopes,
            key_prefix=row.key_prefix,
            name=row.name,
        )
        self.keys.touch_last_used(row.id)
        self.db.commit()
        return principal

    def require_scope(self, principal: ApiKeyPrincipal, scope: str) -> None:
        if not principal.has_scope(scope):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "API key is missing the required scope.",
                details={"required_scope": scope},
            )

    def _build_key_row(
        self,
        *,
        workspace_id: uuid.UUID,
        name: str,
        scopes: list[str],
        created_by: uuid.UUID,
        expires_at: datetime | None,
    ) -> tuple[str, ApiKey]:
        plaintext = generate_api_key_secret()
        row = ApiKey(
            workspace_id=workspace_id,
            name=name,
            key_prefix=display_prefix(plaintext),
            last_four=last_four(plaintext),
            secret_hash=hash_api_key(plaintext, settings=self.settings),
            scopes=scopes,
            created_by=created_by,
            expires_at=expires_at,
        )
        return plaintext, row

    @staticmethod
    def _require_tenant_workspace(workspace: Workspace) -> None:
        if workspace.kind != WorkspaceKind.TENANT.value:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")

    @staticmethod
    def _validate_expiry(expires_at: datetime | None) -> datetime | None:
        if expires_at is None:
            return None
        when = (
            expires_at
            if expires_at.tzinfo is not None
            else expires_at.replace(tzinfo=timezone.utc)
        )
        if when <= datetime.now(timezone.utc):
            raise AppError(ErrorCategory.VALIDATION, "expires_at must be in the future.")
        return when
