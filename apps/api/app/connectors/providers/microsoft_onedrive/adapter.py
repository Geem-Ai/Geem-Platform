"""Microsoft OneDrive connector adapter (Phase 9E)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
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
from app.connectors.models import AppConnection, ConnectorItem
from app.connectors.oauth_tokens import apply_token_response, expires_at_from_credentials
from app.connectors.providers.microsoft_onedrive.client import (
    MicrosoftOneDriveClient,
    build_authorization_url,
)
from app.connectors.providers.microsoft_onedrive.formats import require_supported_mime
from app.connectors.providers.microsoft_onedrive.identity import compose_external_id
from app.connectors.providers.microsoft_onedrive.ingest import MicrosoftOneDriveIngestBridge
from app.connectors.providers.microsoft_onedrive.resolve import (
    resolve_microsoft_onedrive_selections,
)
from app.connectors.providers.microsoft_onedrive.scopes import (
    ONEDRIVE_OAUTH_PROMPT,
    auth_tenant_for_account_kind,
    oauth_scopes_for_tenant,
)
from app.connectors.providers.microsoft_onedrive.picker_auth import (
    apply_account_kind_fields,
)
from app.connectors.providers.microsoft_onedrive.subscription import (
    decode_validation_token,
    ensure_subscription,
    validate_notification_client_state,
)
from app.connectors.providers.microsoft_onedrive.token import ensure_fresh_access
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

CONNECTOR_KEY = "microsoft_onedrive"


@dataclass
class MicrosoftOneDriveConnector:
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
        return self._settings().microsoft_onedrive_configured

    @property
    def unavailable_reason(self) -> str | None:
        if self.is_configured():
            return None
        return ErrorCategory.MICROSOFT_ONEDRIVE_NOT_CONFIGURED.value

    def _client(
        self,
        access_token: str | None = None,
        *,
        tenant: str | None = None,
    ) -> MicrosoftOneDriveClient:
        factory = self.client_factory or MicrosoftOneDriveClient
        return factory(
            settings=self._settings(),
            access_token=access_token,
            tenant=tenant or self._settings().microsoft_onedrive_tenant,
        )

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
                ErrorCategory.MICROSOFT_ONEDRIVE_NOT_CONFIGURED,
                "Microsoft OneDrive OAuth is not configured.",
            )
        settings = self._settings()
        _ = reconnect
        tenant = settings.microsoft_onedrive_tenant.strip() or "organizations"
        scopes = oauth_scopes_for_tenant(tenant)
        url = build_authorization_url(
            client_id=settings.microsoft_onedrive_client_id.strip(),
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes,
            tenant=tenant,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            prompt=prompt or ONEDRIVE_OAUTH_PROMPT,
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
                ErrorCategory.MICROSOFT_ONEDRIVE_NOT_CONFIGURED,
                "Microsoft OneDrive OAuth is not configured.",
            )
        settings = self._settings()
        tenant = settings.microsoft_onedrive_tenant.strip() or "organizations"
        client = self._client(tenant=tenant)
        try:
            # Omit scope on exchange — same pattern as Google Drive. Re-sending
            # mixed Graph + OneDrive.ReadOnly scopes causes MSA 400s.
            token_payload = client.exchange_code(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
            access = str(token_payload["access_token"])
            me = client.get_me(access_token=access)
            drive = client.get_drive(access_token=access)
        finally:
            client.close()

        credentials = apply_token_response({}, token_payload)
        account_id = me.get("id")
        display = me.get("displayName") or me.get("userPrincipalName") or me.get("mail")
        upn = me.get("userPrincipalName") or me.get("mail")
        if account_id:
            credentials["account_id"] = account_id
        if upn:
            credentials["upn"] = upn
        credentials["tenant_id"] = tenant
        drive_id = drive.get("id")
        drive_type = drive.get("driveType")
        drive_web_url = drive.get("webUrl")
        if drive_id:
            credentials["drive_id"] = drive_id
            credentials["drive_type"] = drive_type
            credentials["drive_web_url"] = drive_web_url
        kind = apply_account_kind_fields(
            credentials,
            web_url=str(drive_web_url or "") or None,
            drive_type=str(drive_type or "") or None,
            settings_tenant=tenant,
        )
        credentials["account_kind"] = kind
        credentials["auth_tenant"] = auth_tenant_for_account_kind(
            account_kind=kind,
            settings_tenant=tenant,
        )
        scope = token_payload.get("scope")
        if scope:
            credentials["granted_scopes"] = (
                scope.split() if isinstance(scope, str) else list(scope)
            )

        # Seed encrypted sync_state with drive identity (no delta yet).
        # Caller persists credentials; sync_state is set on activate via adapter
        # post-hook or first sync. Store drive fields in credentials for picker.
        return OAuthCompletionResult(
            credentials=credentials,
            external_account_id=str(account_id) if account_id else None,
            external_account_name=str(upn or display) if (upn or display) else None,
            display_name=str(upn or display) if (upn or display) else None,
            credentials_expires_at=expires_at_from_credentials(credentials),
        )

    def refresh_credentials(
        self, *, credentials: dict[str, Any]
    ) -> OAuthCompletionResult:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                "Microsoft OneDrive refresh token is missing.",
            )
        tenant = str(
            credentials.get("tenant_id")
            or self._settings().microsoft_onedrive_tenant
        )
        client = self._client(tenant=tenant)
        try:
            token_payload = client.refresh_access_token(
                refresh_token=str(refresh_token)
            )
        finally:
            client.close()
        merged = apply_token_response(credentials, token_payload)
        return OAuthCompletionResult(
            credentials=merged,
            external_account_id=credentials.get("account_id"),
            external_account_name=credentials.get("upn"),
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
        return resolve_microsoft_onedrive_selections(
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
                error_code=ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED.value,
                error_message="Missing access token.",
            )
        tenant = str(
            credentials.get("tenant_id") or self._settings().microsoft_onedrive_tenant
        )
        client = self._client(access_token=str(token), tenant=tenant)
        try:
            client.get_me()
            client.get_drive()
            return HealthCheckResult(health=ConnectionHealth.HEALTHY)
        except AppError as exc:
            if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_RATE_LIMITED:
                return HealthCheckResult(
                    health=ConnectionHealth.DEGRADED,
                    error_code=exc.category.value,
                    error_message=exc.message,
                )
            if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED:
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
        state = sync_state if isinstance(sync_state, dict) else {}
        sub = state.get("graph_subscription")
        token = (credentials or {}).get("access_token")
        if isinstance(sub, dict) and sub.get("id") and token:
            tenant = str(
                (credentials or {}).get("tenant_id")
                or self._settings().microsoft_onedrive_tenant
            )
            client = self._client(access_token=str(token), tenant=tenant)
            try:
                client.delete_subscription(subscription_id=str(sub["id"]))
            except Exception:  # noqa: BLE001
                logger.info(
                    "microsoft_onedrive_subscription_delete_failed",
                    extra={"connection_id": str(connection_id)},
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
                ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
                "Microsoft OneDrive sync requires a database session.",
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
        drive_id = str(
            state.get("drive_id") or fresh.get("drive_id") or ""
        ).strip()
        if not drive_id:
            # Resolve drive if missing from older connections.
            tenant = str(fresh.get("tenant_id") or settings.microsoft_onedrive_tenant)
            probe = self._client(
                access_token=str(fresh.get("access_token")), tenant=tenant
            )
            try:
                drive = probe.get_drive()
            finally:
                probe.close()
            drive_id = str(drive.get("id") or "")
            if not drive_id:
                raise AppError(
                    ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
                    "Connected OneDrive drive could not be resolved.",
                )
            state["drive_id"] = drive_id
            state["drive_type"] = drive.get("driveType")
            state["drive_web_url"] = drive.get("webUrl")
            apply_account_kind_fields(
                state,
                web_url=str(drive.get("webUrl") or "") or None,
                drive_type=str(drive.get("driveType") or "") or None,
                settings_tenant=settings.microsoft_onedrive_tenant,
            )
            cred_svc.set_sync_state(connection, state)
            db.flush()

        tenant = str(
            fresh.get("auth_tenant")
            or fresh.get("tenant_id")
            or settings.microsoft_onedrive_tenant
        )
        client = self._client(
            access_token=str(fresh.get("access_token")), tenant=tenant
        )
        bridge = MicrosoftOneDriveIngestBridge(
            db, settings=settings, connected_drive_id=drive_id
        )

        seen = created = updated = deleted = failed = 0
        partial = False
        error_code: str | None = None
        error_message: str | None = None

        try:
            # Race-safe baseline: capture delta cursor before initial ingest.
            if not state.get("delta_link") and not state.get("_delta_baseline"):
                baseline = client.delta(drive_id=drive_id)
                # Drain to a stable deltaLink without processing (untracked).
                page = baseline
                while True:
                    next_link = page.get("@odata.nextLink")
                    delta_link = page.get("@odata.deltaLink")
                    if next_link:
                        page = client.delta(drive_id=drive_id, delta_link=next_link)
                        continue
                    if delta_link:
                        state["_delta_baseline"] = delta_link
                        break
                    break
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

            tracked_by_ext = {
                row.external_id: row
                for row in db.scalars(
                    select(ConnectorItem).where(
                        ConnectorItem.workspace_id == workspace_id,
                        ConnectorItem.app_connection_id == connection_id,
                    )
                ).all()
            }

            # After initial ingest, promote baseline → working delta_link.
            if state.get("_delta_baseline") and not state.get("delta_link"):
                state["delta_link"] = state.pop("_delta_baseline")
                # Consume changes since baseline for tracked items.
                try:
                    s, c, u, d, f, p, new_state = self._consume_delta(
                        client=client,
                        bridge=bridge,
                        drive_id=drive_id,
                        state=state,
                        tracked_by_ext=tracked_by_ext,
                        workspace_id=workspace_id,
                        connection_id=connection_id,
                        actor_id=connection.connected_by_user_id,
                        cred_svc=cred_svc,
                        connection=connection,
                        db=db,
                    )
                    seen += s
                    created += c
                    updated += u
                    deleted += d
                    failed += f
                    partial = partial or p
                    state = new_state
                except AppError as exc:
                    if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_DELTA_RESYNC_REQUIRED:
                        s, c, u, d, f, p, state = self._resync_tracked(
                            client=client,
                            bridge=bridge,
                            drive_id=drive_id,
                            state=state,
                            tracked_by_ext=tracked_by_ext,
                            workspace_id=workspace_id,
                            connection_id=connection_id,
                            actor_id=connection.connected_by_user_id,
                            cred_svc=cred_svc,
                            connection=connection,
                            db=db,
                        )
                        seen += s
                        created += c
                        updated += u
                        deleted += d
                        failed += f
                        partial = partial or p
                    else:
                        raise
            elif state.get("delta_link"):
                try:
                    s, c, u, d, f, p, new_state = self._consume_delta(
                        client=client,
                        bridge=bridge,
                        drive_id=drive_id,
                        state=state,
                        tracked_by_ext=tracked_by_ext,
                        workspace_id=workspace_id,
                        connection_id=connection_id,
                        actor_id=connection.connected_by_user_id,
                        cred_svc=cred_svc,
                        connection=connection,
                        db=db,
                    )
                    seen += s
                    created += c
                    updated += u
                    deleted += d
                    failed += f
                    partial = partial or p
                    state = new_state
                except AppError as exc:
                    if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_DELTA_RESYNC_REQUIRED:
                        s, c, u, d, f, p, state = self._resync_tracked(
                            client=client,
                            bridge=bridge,
                            drive_id=drive_id,
                            state=state,
                            tracked_by_ext=tracked_by_ext,
                            workspace_id=workspace_id,
                            connection_id=connection_id,
                            actor_id=connection.connected_by_user_id,
                            cred_svc=cred_svc,
                            connection=connection,
                            db=db,
                        )
                        seen += s
                        created += c
                        updated += u
                        deleted += d
                        failed += f
                        partial = partial or p
                    else:
                        raise

            # Ensure Graph subscription.
            routing_token = None
            if connection.webhook_routing_token_encrypted:
                try:
                    routing_token = decrypt_secret(
                        connection.webhook_routing_token_encrypted,
                        settings=settings,
                    )
                except Exception:  # noqa: BLE001
                    routing_token = None
            if routing_token and drive_id:
                try:
                    state = ensure_subscription(
                        client,
                        sync_state=state,
                        drive_id=drive_id,
                        routing_token=routing_token,
                        settings=settings,
                    )
                    cred_svc.set_sync_state(connection, state)
                    db.flush()
                except AppError as exc:
                    if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED:
                        raise
                    partial = True
                    error_code = (
                        ErrorCategory.MICROSOFT_ONEDRIVE_SUBSCRIPTION_FAILED.value
                    )
                    error_message = exc.message
                    logger.info(
                        "microsoft_onedrive_subscription_ensure_failed",
                        extra={"connection_id": str(connection_id)},
                    )
        except AppError as exc:
            if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED:
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

    def _consume_delta(
        self,
        *,
        client: MicrosoftOneDriveClient,
        bridge: MicrosoftOneDriveIngestBridge,
        drive_id: str,
        state: dict[str, Any],
        tracked_by_ext: dict[str, ConnectorItem],
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        cred_svc: ConnectorCredentialService,
        connection: AppConnection,
        db: Session,
    ) -> tuple[int, int, int, int, int, bool, dict[str, Any]]:
        seen = created = updated = deleted = failed = 0
        partial = False
        link = state.get("delta_link")
        working = dict(state)

        while True:
            page = client.delta(drive_id=drive_id, delta_link=link)
            for entry in page.get("value") or []:
                if not isinstance(entry, dict):
                    continue
                item_id = str(entry.get("id") or "")
                parent = (
                    entry.get("parentReference")
                    if isinstance(entry.get("parentReference"), dict)
                    else {}
                )
                entry_drive = str(parent.get("driveId") or drive_id)
                if not item_id:
                    continue
                try:
                    external_id = compose_external_id(entry_drive, item_id)
                except AppError:
                    continue
                item = tracked_by_ext.get(external_id)
                if item is None:
                    continue
                seen += 1
                if entry.get("deleted") is not None:
                    bridge.mark_item_unavailable(item)
                    deleted += 1
                    continue
                try:
                    file_facet = (
                        entry.get("file") if isinstance(entry.get("file"), dict) else {}
                    )
                    if entry.get("folder") is not None and not file_facet:
                        continue
                    if file_facet or entry.get("file"):
                        require_supported_mime(
                            file_facet.get("mimeType"), name=entry.get("name")
                        )
                except AppError:
                    failed += 1
                    partial = True
                    continue
                if entry.get("name"):
                    item.name = str(entry["name"])
                action = bridge.ingest_tracked_item(
                    workspace_id=workspace_id,
                    connection_id=connection_id,
                    item=item,
                    client=client,
                    actor_id=actor_id,
                    force=False,
                )
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1
                elif action == "failed":
                    failed += 1
                    partial = True
                elif action == "skipped":
                    updated += 1

            next_link = page.get("@odata.nextLink")
            delta_link = page.get("@odata.deltaLink")
            if next_link:
                # Do not advance persisted cursor until full set consumed.
                link = next_link
                continue
            if delta_link:
                working["delta_link"] = delta_link
                working.pop("_delta_baseline", None)
                cred_svc.set_sync_state(connection, working)
                db.flush()
            break

        return seen, created, updated, deleted, failed, partial, working

    def _resync_tracked(
        self,
        *,
        client: MicrosoftOneDriveClient,
        bridge: MicrosoftOneDriveIngestBridge,
        drive_id: str,
        state: dict[str, Any],
        tracked_by_ext: dict[str, ConnectorItem],
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        cred_svc: ConnectorCredentialService,
        connection: AppConnection,
        db: Session,
    ) -> tuple[int, int, int, int, int, bool, dict[str, Any]]:
        """410 Gone / resyncRequired — reconcile tracked subset, fresh deltaLink."""
        seen = created = updated = deleted = failed = 0
        partial = False
        working = dict(state)
        working.pop("delta_link", None)
        working.pop("_delta_baseline", None)

        still_present: set[str] = set()
        # Fresh delta enumeration to obtain new deltaLink; only act on tracked.
        link: str | None = None
        while True:
            page = client.delta(drive_id=drive_id, delta_link=link)
            for entry in page.get("value") or []:
                if not isinstance(entry, dict):
                    continue
                item_id = str(entry.get("id") or "")
                parent = (
                    entry.get("parentReference")
                    if isinstance(entry.get("parentReference"), dict)
                    else {}
                )
                entry_drive = str(parent.get("driveId") or drive_id)
                if not item_id:
                    continue
                try:
                    external_id = compose_external_id(entry_drive, item_id)
                except AppError:
                    continue
                item = tracked_by_ext.get(external_id)
                if item is None:
                    continue
                if entry.get("deleted") is not None:
                    continue
                still_present.add(external_id)
            next_link = page.get("@odata.nextLink")
            delta_link = page.get("@odata.deltaLink")
            if next_link:
                link = next_link
                continue
            if delta_link:
                working["delta_link"] = delta_link
            break

        for external_id, item in tracked_by_ext.items():
            seen += 1
            if item.status == ConnectorItemStatus.UNAVAILABLE.value:
                continue
            if external_id not in still_present:
                # Revalidate via get_item — may still exist outside delta page window.
                try:
                    action = bridge.ingest_tracked_item(
                        workspace_id=workspace_id,
                        connection_id=connection_id,
                        item=item,
                        client=client,
                        actor_id=actor_id,
                        force=False,
                    )
                    if action == "failed":
                        # ingest marks unavailable on not found
                        if item.status == ConnectorItemStatus.UNAVAILABLE.value:
                            deleted += 1
                        else:
                            failed += 1
                            partial = True
                    elif action == "created":
                        created += 1
                    elif action == "updated":
                        updated += 1
                except Exception:  # noqa: BLE001
                    failed += 1
                    partial = True
                continue
            action = bridge.ingest_tracked_item(
                workspace_id=workspace_id,
                connection_id=connection_id,
                item=item,
                client=client,
                actor_id=actor_id,
                force=False,
            )
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            elif action == "failed":
                failed += 1
                partial = True

        cred_svc.set_sync_state(connection, working)
        db.flush()
        return seen, created, updated, deleted, failed, partial, working

    def verify_and_handle_webhook(
        self,
        *,
        request: WebhookRequestContext,
        credentials: dict[str, Any] | None,
    ) -> WebhookHandleResult:
        _ = credentials
        # Graph validation handshake — respond immediately, no sync.
        validation = decode_validation_token(
            request.query_params.get("validationToken")
            or request.query_params.get("validationtoken")
        )
        if validation is not None:
            return WebhookHandleResult(
                accepted=True,
                ignore=True,
                enqueue=False,
                http_status=200,
                response_body=validation.encode("utf-8"),
                response_headers={"Content-Type": "text/plain"},
            )

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
            sync_state = ConnectorCredentialService(db).get_sync_state(row) or {}
            expected_sub = None
            sub = sync_state.get("graph_subscription")
            if isinstance(sub, dict):
                expected_sub = sub.get("id")

            try:
                payload = json.loads(request.raw_body.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return WebhookHandleResult(
                    accepted=False,
                    error_code=ErrorCategory.CONNECTOR_WEBHOOK_INVALID.value,
                    http_status=400,
                )

            notifications = payload.get("value")
            if not isinstance(notifications, list):
                notifications = [payload] if payload else []

            accepted_any = False
            event_ids: list[str] = []
            for note in notifications:
                if not isinstance(note, dict):
                    continue
                if expected_sub and str(note.get("subscriptionId") or "") != str(
                    expected_sub
                ):
                    continue
                if not validate_notification_client_state(
                    notification=note, sync_state=sync_state
                ):
                    continue
                accepted_any = True
                if note.get("subscriptionId"):
                    event_ids.append(str(note["subscriptionId"]))
                if note.get("resource"):
                    event_ids.append(str(note.get("resourceData", {}).get("id") or ""))

            if not accepted_any:
                return WebhookHandleResult(
                    accepted=False,
                    error_code=ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED.value,
                    http_status=401,
                )

            idem = (
                f"msod:{request.connection_id}:"
                f"{hash(tuple(event_ids)) & 0xFFFFFFFF:x}"
                if event_ids
                else f"msod:{request.connection_id}:{uuid.uuid4()}"
            )
            return WebhookHandleResult(
                accepted=True,
                enqueue=True,
                enqueue_payload={"kind": "microsoft_onedrive_change"},
                provider_event_id=event_ids[0] if event_ids else None,
                idempotency_key=idem,
                http_status=202,
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


def register_microsoft_onedrive_connector(
    registry: Any | None = None,
    *,
    settings: Settings | None = None,
) -> MicrosoftOneDriveConnector:
    """Register (or replace) the Microsoft OneDrive adapter."""
    from app.connectors.registry import connector_registry

    reg = registry or connector_registry
    adapter = MicrosoftOneDriveConnector(settings=settings)
    if reg.has(CONNECTOR_KEY):
        reg.unregister(CONNECTOR_KEY)
    reg.register(adapter)
    return adapter
