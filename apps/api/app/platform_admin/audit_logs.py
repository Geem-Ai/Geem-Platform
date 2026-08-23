"""Platform Admin audit log queries (Phase 12G)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.audit.sanitize import redact_audit_metadata_for_read
from app.core.errors import AppError, ErrorCategory
from app.documents.repository import ilike_contains_pattern
from app.identity.models import PlatformRole, User
from app.platform_admin.authz import require_platform_admin_user
from app.platform_admin.schemas import (
    PlatformAuditActorOut,
    PlatformAuditListItemOut,
    PlatformAuditListResponse,
    PlatformAuditLogDetailOut,
    PlatformAuditResourceOut,
    PlatformAuditWorkspaceOut,
)
from app.workspaces.models import Workspace


class PlatformAuditLogsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_logs(
        self,
        actor: User,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        scope: str | None = None,
    ) -> PlatformAuditListResponse:
        require_platform_admin_user(actor)
        stmt = self._select_stmt()
        stmt = self._apply_filters(
            stmt,
            search=search,
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            from_at=from_at,
            to_at=to_at,
            scope=scope,
        )
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return PlatformAuditListResponse(
            items=[self._list_item(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_log(self, actor: User, audit_id: uuid.UUID) -> PlatformAuditLogDetailOut:
        require_platform_admin_user(actor)
        row = self.db.execute(self._select_stmt().where(AuditLog.id == audit_id)).one_or_none()
        if row is None:
            raise AppError(ErrorCategory.NOT_FOUND, "Audit log not found.")
        audit, actor_email, ws_name, ws_slug = row
        metadata = redact_audit_metadata_for_read(audit.extra or {})
        return PlatformAuditLogDetailOut(
            id=audit.id,
            created_at=audit.created_at,
            actor=self._actor_out(audit, actor_email),
            workspace=self._workspace_out(audit, ws_name, ws_slug),
            action=audit.action,
            resource=PlatformAuditResourceOut(
                entity_type=audit.entity_type,
                entity_id=audit.entity_id,
            ),
            request_id=audit.request_id,
            summary=self._summary(audit.action, metadata),
            metadata=metadata,
        )

    def recent_platform_activity(self, *, limit: int) -> list[PlatformAuditListItemOut]:
        rows = self.db.execute(
            self._select_stmt()
            .where(
                or_(
                    AuditLog.workspace_id.is_(None),
                    User.platform_role == PlatformRole.ADMIN.value,
                )
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
        return [self._list_item(row) for row in rows]

    def _select_stmt(self):
        return (
            select(AuditLog, User.email, Workspace.name, Workspace.slug)
            .select_from(AuditLog)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .outerjoin(Workspace, Workspace.id == AuditLog.workspace_id)
        )

    def _apply_filters(
        self,
        stmt,
        *,
        search: str | None,
        actor_user_id: uuid.UUID | None,
        workspace_id: uuid.UUID | None,
        action: str | None,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        from_at: datetime | None,
        to_at: datetime | None,
        scope: str | None,
    ):
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if workspace_id is not None:
            stmt = stmt.where(AuditLog.workspace_id == workspace_id)
        if action:
            stmt = stmt.where(AuditLog.action == action.strip())
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type.strip())
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if from_at is not None:
            stmt = stmt.where(AuditLog.created_at >= from_at)
        if to_at is not None:
            stmt = stmt.where(AuditLog.created_at <= to_at)
        if (scope or "").strip().lower() == "platform":
            stmt = stmt.where(AuditLog.workspace_id.is_(None))
        if search:
            pattern = ilike_contains_pattern(search)
            stmt = stmt.where(
                or_(
                    AuditLog.action.ilike(pattern),
                    AuditLog.entity_type.ilike(pattern),
                    User.email.ilike(pattern),
                    Workspace.name.ilike(pattern),
                    Workspace.slug.ilike(pattern),
                )
            )
        return stmt

    def _actor_out(self, row: AuditLog, email: str | None) -> PlatformAuditActorOut | None:
        if row.actor_user_id is None and row.actor_api_key_id is None:
            return None
        return PlatformAuditActorOut(
            user_id=row.actor_user_id,
            api_key_id=row.actor_api_key_id,
            email=email or None,
        )

    def _workspace_out(
        self, row: AuditLog, name: str | None, slug: str | None
    ) -> PlatformAuditWorkspaceOut | None:
        if row.workspace_id is None:
            return None
        return PlatformAuditWorkspaceOut(
            workspace_id=row.workspace_id,
            name=name or "",
            slug=slug or "",
        )

    def _summary(self, action: str, metadata: dict) -> str | None:
        for key in ("reason", "summary", "message"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return action

    def _list_item(self, row) -> PlatformAuditListItemOut:
        audit, actor_email, ws_name, ws_slug = row
        metadata = redact_audit_metadata_for_read(audit.extra or {})
        return PlatformAuditListItemOut(
            id=audit.id,
            created_at=audit.created_at,
            actor=self._actor_out(audit, actor_email),
            workspace=self._workspace_out(audit, ws_name, ws_slug),
            action=audit.action,
            resource=PlatformAuditResourceOut(
                entity_type=audit.entity_type,
                entity_id=audit.entity_id,
            ),
            request_id=audit.request_id,
            summary=self._summary(audit.action, metadata),
        )
