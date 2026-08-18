"""Google Drive connector adapter (Phase 9D)."""

from __future__ import annotations

import hashlib
import base64
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.crypto import decrypt_secret
from app.connectors.adapters import (
    ConnectorCapabilities,
    HealthCheckResult,
    OAuthAuthorizationRequest,
    OAuthCompletionResult,
    SyncResult,
    WebhookHandleResult,
    WebhookRequestContext,
)
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.items import ConnectorItemService
from app.connectors.models import AppConnection, ConnectorItem
from app.connectors.providers.google_drive.client import (
    GoogleDriveClient,
    build_authorization_url,
)
from app.connectors.providers.google_drive.formats import require_supported_mime
from app.connectors.providers.google_drive.ingest import GoogleDriveIngestBridge
from app.connectors.providers.google_drive.resolve import resolve_google_drive_selections
from app.connectors.providers.google_drive.scopes import (
    GOOGLE_OAUTH_PROMPT,
    requires_reauthorization,
    scopes_for_mode,
)
from app.connectors.providers.google_drive.token import (
    apply_token_response,
    ensure_fresh_access,
    expires_at_from_credentials,
)
from app.connectors.providers.google_drive.watch import (
    ensure_changes_watch,
    validate_webhook_headers,
)
from app.connectors.repository import ConnectorRepository
from app.connectors.types import (
    ConnectionHealth,
    ConnectorAuthMode,
    ConnectorItemStatus,
    ConnectorKind,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.models import ExpertSource, ExpertSourceStatus, ExpertSourceType

logger = logging.getLogger(__name__)

CONNECTOR_KEY = "google_drive"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass
class GoogleDriveConnector:
    key: str = CONNECTOR_KEY
    kind: ConnectorKind = ConnectorKind.KNOWLEDGE_SOURCE
    auth_mode: ConnectorAuthMode = ConnectorAuthMode.OAUTH2
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            supports_oauth=True,
            supports_credentials=False,
            supports_sync=True,
            supports_webhooks=True,
            supports_health_check=True,
        )
    )
    settings: Settings | None = None
    client_factory: Any = None

    def _settings(self) -> Settings:
        return self.settings or get_settings()

    def is_configured(self) -> bool:
        return self._settings().google_drive_configured

    @property
    def unavailable_reason(self) -> str | None:
        if self.is_configured():
            return None
        return ErrorCategory.GOOGLE_DRIVE_NOT_CONFIGURED.value

    def _client(self, access_token: str | None = None) -> GoogleDriveClient:
        factory = self.client_factory or GoogleDriveClient
        return factory(settings=self._settings(), access_token=access_token)

    def build_authorization_request(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
        prompt: str | None = None,
        reconnect: bool = False,
    ) -> OAuthAuthorizationRequest:
        if not self.is_configured():
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_NOT_CONFIGURED,
                "Google Drive OAuth is not configured.",
            )
        settings = self._settings()
        scopes = scopes_for_mode(settings.google_drive_scope_mode)
        # Always request consent so Google returns a refresh_token. After disconnect
        # secrets are cleared; select_account alone often omits refresh_token.
        # Include select_account so the user can link a different Google email.
        _ = reconnect
        effective_prompt = prompt or GOOGLE_OAUTH_PROMPT
        url = build_authorization_url(
            client_id=settings.google_drive_client_id.strip(),
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            prompt=effective_prompt,
            include_granted_scopes=True,
        )
        return OAuthAuthorizationRequest(
            authorization_url=url,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

    def complete_authorization(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        state_payload: dict[str, Any] | None = None,
    ) -> OAuthCompletionResult:
        _ = state_payload
        if not self.is_configured():
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_NOT_CONFIGURED,
                "Google Drive OAuth is not configured.",
            )
        client = self._client()
        try:
            token_payload = client.exchange_code(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
            access = str(token_payload["access_token"])
            userinfo = client.get_userinfo(access_token=access)
        finally:
            client.close()

        credentials = apply_token_response({}, token_payload)
        google_sub = userinfo.get("sub")
        email = userinfo.get("email")
        name = userinfo.get("name") or email
        if google_sub:
            credentials["google_sub"] = google_sub
        if email:
            credentials["email"] = email
        scope = token_payload.get("scope")
        if scope:
            granted = scope.split() if isinstance(scope, str) else list(scope)
            credentials["granted_scopes"] = granted
            if requires_reauthorization(
                granted, self._settings().google_drive_scope_mode
            ):
                raise AppError(
                    ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
                    "Granted Google Drive scopes do not match the configured mode.",
                )

        return OAuthCompletionResult(
            credentials=credentials,
            external_account_id=str(google_sub) if google_sub else None,
            external_account_name=str(email or name) if (email or name) else None,
            display_name=str(email or name) if (email or name) else None,
            credentials_expires_at=expires_at_from_credentials(credentials),
        )

    def refresh_credentials(
        self, *, credentials: dict[str, Any]
    ) -> OAuthCompletionResult:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
                "Google Drive refresh token is missing.",
            )
        client = self._client()
        try:
            token_payload = client.refresh_access_token(refresh_token=str(refresh_token))
        finally:
            client.close()
        merged = apply_token_response(credentials, token_payload)
        return OAuthCompletionResult(
            credentials=merged,
            external_account_id=credentials.get("google_sub"),
            external_account_name=credentials.get("email"),
            credentials_expires_at=expires_at_from_credentials(merged),
        )

    def resolve_selected_items(
        self,
        *,
        db: Session,
        connection: AppConnection,
        credentials: dict[str, Any],
        selections: list[Any],
        settings: Settings,
    ) -> list[Any]:
        return resolve_google_drive_selections(
            db=db,
            connection=connection,
            credentials=credentials,
            selections=selections,
            settings=settings,
        )

    def health_check(
        self,
        *,
        credentials: dict[str, Any],
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> HealthCheckResult:
        _ = connection_id, workspace_id
        token = credentials.get("access_token")
        if not token:
            return HealthCheckResult(
                health=ConnectionHealth.FAILED,
                error_code=ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED.value,
                error_message="Missing access token.",
            )
        client = self._client(access_token=str(token))
        try:
            try:
                client.get_about_user()
            except AppError:
                client.list_files_page(page_size=1)
            return HealthCheckResult(health=ConnectionHealth.HEALTHY)
        except AppError as exc:
            if exc.category == ErrorCategory.GOOGLE_DRIVE_RATE_LIMITED:
                return HealthCheckResult(
                    health=ConnectionHealth.DEGRADED,
                    error_code=exc.category.value,
                    error_message=exc.message,
                )
            if exc.category == ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED:
                return HealthCheckResult(
                    health=ConnectionHealth.FAILED,
                    error_code=exc.category.value,
                    error_message=exc.message,
                )
            return HealthCheckResult(
                health=ConnectionHealth.DEGRADED,
                error_code=exc.category.value,
                error_message=exc.message,
            )
        finally:
            client.close()

    def disconnect(
        self,
        *,
        credentials: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
        sync_state: dict[str, Any] | None = None,
    ) -> None:
        _ = workspace_id, connection_id
        state = sync_state
        if state is None and credentials:
            state = credentials.get("_sync_state")
        if not isinstance(state, dict):
            state = {}
        channel_id = state.get("watch_channel_id")
        resource_id = state.get("watch_resource_id")
        token = (credentials or {}).get("access_token")
        if channel_id and resource_id and token:
            client = self._client(access_token=str(token))
            try:
                client.stop_channel(
                    channel_id=str(channel_id), resource_id=str(resource_id)
                )
            finally:
                client.close()

    def sync(
        self,
        *,
        credentials: dict[str, Any],
        sync_state: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
        sync_run_id: uuid.UUID,
        db: Any | None = None,
    ) -> SyncResult:
        _ = sync_run_id
        if db is None:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_SYNC_FAILED,
                "Google Drive sync requires a database session.",
            )
        assert isinstance(db, Session)
        settings = self._settings()
        repo = ConnectorRepository(db)
        cred_svc = ConnectorCredentialService(db, settings=settings)
        connection = repo.get_connection(workspace_id, connection_id, for_update=True)
        if connection is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")

        fresh = ensure_fresh_access(db, connection, credentials, settings)
        state = dict(sync_state or cred_svc.get_sync_state(connection) or {})

        client = self._client(access_token=str(fresh.get("access_token")))
        bridge = GoogleDriveIngestBridge(db, settings=settings)
        items_svc = ConnectorItemService(db)

        seen = created = updated = deleted = failed = 0
        partial = False
        error_code: str | None = None
        error_message: str | None = None

        try:
            # Race-safe: capture start page token before initial ingest.
            if not state.get("start_page_token"):
                state["start_page_token"] = client.get_start_page_token()
                cred_svc.set_sync_state(connection, state)
                db.flush()

            tracked = list(
                db.scalars(
                    select(ConnectorItem).where(
                        ConnectorItem.workspace_id == workspace_id,
                        ConnectorItem.app_connection_id == connection_id,
                        ConnectorItem.status == ConnectorItemStatus.ACTIVE.value,
                    )
                ).all()
            )

            for item in tracked:
                needs_ingest = item.current_document_id is None or self._item_pending_sources(
                    db, item
                )
                if not needs_ingest:
                    continue
                seen += 1
                action = bridge.ingest_tracked_item(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    item=item,
                    client=client,
                    actor_id=connection.connected_by_user_id,
                    force=item.current_document_id is None,
                )
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1
                elif action == "failed":
                    failed += 1
                    partial = True

            # Incremental changes for tracked external ids only.
            page_token = state.get("start_page_token")
            tracked_ids = {item.external_id for item in tracked}
            # Refresh tracked map after initial ingest.
            tracked_by_ext = {
                row.external_id: row
                for row in db.scalars(
                    select(ConnectorItem).where(
                        ConnectorItem.workspace_id == workspace_id,
                        ConnectorItem.app_connection_id == connection_id,
                    )
                ).all()
            }
            tracked_ids = set(tracked_by_ext.keys())

            while page_token:
                page = client.list_changes(page_token=str(page_token))
                for change in page.get("changes") or []:
                    file_id = change.get("fileId")
                    if not file_id or file_id not in tracked_ids:
                        continue
                    item = tracked_by_ext.get(file_id)
                    if item is None:
                        continue
                    seen += 1
                    removed = bool(change.get("removed"))
                    file_meta = change.get("file") or {}
                    if removed or file_meta.get("trashed"):
                        bridge.mark_item_unavailable(item)
                        deleted += 1
                        continue
                    # Apply authoritative metadata from change when present.
                    if file_meta.get("name"):
                        item.name = str(file_meta["name"])
                    if file_meta.get("mimeType"):
                        item.mime_type = file_meta["mimeType"]
                    try:
                        if file_meta.get("mimeType"):
                            require_supported_mime(file_meta.get("mimeType"))
                    except AppError:
                        failed += 1
                        partial = True
                        continue
                    action = bridge.ingest_tracked_item(
                        workspace_id=workspace_id,
                        connection_id=connection_id,
                        item=item,
                        client=client,
                        actor_id=connection.connected_by_user_id,
                        force=True,
                    )
                    if action == "created":
                        created += 1
                    elif action == "updated":
                        updated += 1
                    elif action == "failed":
                        failed += 1
                        partial = True
                    else:
                        # rename-only already applied above
                        updated += 1

                next_token = page.get("nextPageToken")
                new_start = page.get("newStartPageToken")
                if next_token:
                    page_token = next_token
                else:
                    if new_start:
                        state["start_page_token"] = new_start
                    page_token = None
                # Persist token after each successful page.
                cred_svc.set_sync_state(connection, state)
                db.flush()

            # Ensure watch is active.
            routing_token = None
            if connection.webhook_routing_token_encrypted:
                try:
                    routing_token = decrypt_secret(
                        connection.webhook_routing_token_encrypted,
                        settings=settings,
                    )
                except Exception:  # noqa: BLE001
                    routing_token = None
            if routing_token and state.get("start_page_token"):
                try:
                    state = ensure_changes_watch(
                        client,
                        sync_state=state,
                        page_token=str(state["start_page_token"]),
                        routing_token=routing_token,
                        settings=settings,
                    )
                    cred_svc.set_sync_state(connection, state)
                    db.flush()
                except AppError as exc:
                    partial = True
                    error_code = exc.category.value
                    error_message = exc.message
                    logger.info(
                        "google_drive_watch_ensure_failed",
                        extra={"connection_id": str(connection_id)},
                    )

            # Persist any refreshed credentials already written by ensure_fresh_access.
            _ = items_svc
        except AppError as exc:
            if exc.category == ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED:
                raise
            partial = True
            error_code = exc.category.value
            error_message = exc.message
            failed += 1
        finally:
            client.close()

        return SyncResult(
            items_seen=seen,
            items_created=created,
            items_updated=updated,
            items_deleted=deleted,
            items_failed=failed,
            sync_state=state,
            partial=partial,
            error_code=error_code,
            error_message=error_message,
        )

    def verify_and_handle_webhook(
        self,
        *,
        request: WebhookRequestContext,
        credentials: dict[str, Any] | None,
    ) -> WebhookHandleResult:
        _ = credentials
        # Load sync_state via connection_id from request (dispatcher provides ids).
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            repo = ConnectorRepository(db)
            row = repo.get_connection(request.workspace_id, request.connection_id)
            if row is None:
                return WebhookHandleResult(
                    accepted=False,
                    error_code=ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED.value,
                    http_status=401,
                )
            sync_state = ConnectorCredentialService(db).get_sync_state(row)
            ok, resource_state = validate_webhook_headers(
                headers=request.headers, sync_state=sync_state
            )
            if not ok:
                return WebhookHandleResult(
                    accepted=False,
                    error_code=ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED.value,
                    http_status=401,
                )
            # sync = channel verification / lifecycle — acknowledge, do not enqueue.
            if resource_state in {"sync", ""}:
                return WebhookHandleResult(
                    accepted=True,
                    ignore=True,
                    enqueue=False,
                    http_status=200,
                    response_body=b"",
                )
            if resource_state == "change":
                return WebhookHandleResult(
                    accepted=True,
                    enqueue=True,
                    enqueue_payload={"kind": "google_drive_change"},
                    provider_event_id=request.headers.get("x-goog-message-number"),
                    idempotency_key=(
                        f"gdrive:{request.connection_id}:"
                        f"{request.headers.get('x-goog-message-number') or uuid.uuid4()}"
                    ),
                    http_status=200,
                    response_body=b"",
                )
            return WebhookHandleResult(
                accepted=True,
                ignore=True,
                enqueue=False,
                http_status=200,
                response_body=b"",
            )
        finally:
            db.close()

    @staticmethod
    def _item_pending_sources(db: Session, item: ConnectorItem) -> bool:
        item_id = str(item.id)
        rows = list(
            db.scalars(
                select(ExpertSource).where(
                    ExpertSource.type == ExpertSourceType.CONNECTOR.value,
                    ExpertSource.deleted_at.is_(None),
                    ExpertSource.status.in_(
                        [
                            ExpertSourceStatus.PENDING.value,
                            ExpertSourceStatus.PROCESSING.value,
                            ExpertSourceStatus.STALE.value,
                        ]
                    ),
                )
            ).all()
        )
        return any(
            isinstance(s.config, dict)
            and str(s.config.get("connector_item_id") or "") == item_id
            for s in rows
        )


def register_google_drive_connector(
    registry: Any | None = None,
    *,
    settings: Settings | None = None,
) -> GoogleDriveConnector:
    """Register (or replace) the Google Drive adapter. Safe if already registered."""
    from app.connectors.registry import connector_registry

    reg = registry or connector_registry
    adapter = GoogleDriveConnector(settings=settings)
    if reg.has(CONNECTOR_KEY):
        reg.unregister(CONNECTOR_KEY)
    reg.register(adapter)
    return adapter
