"""Workspace-facing OpenWA session lifecycle + channel settings."""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.models import AppInstallation, AppInstallationStatus, CatalogApp
from app.apps_catalog.policy import can_manage_apps
from app.apps_catalog.repository import AppCatalogRepository
from app.common.crypto import decrypt_secret
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection, ChannelBinding
from app.connectors.providers.openwa.client import OpenWAClient
from app.connectors.providers.openwa.schemas import (
    OPENWA_WEBHOOK_EVENTS,
    OpenWAQrResponse,
    OpenWASession,
    OpenWASessionStatus,
)
from app.connectors.providers.openwa.text import normalize_whatsapp_phone
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.sanitize import sanitize_error_message
from app.connectors.schemas import (
    AppConnectionListOut,
    WhatsAppConnectionOut,
    to_connection_out,
)
from app.connectors.service import ConnectorConnectionService, _now, _transition
from app.connectors.types import (
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.experts.access import ExpertAccessService
from app.experts.policy import ExpertAction
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)

CONNECTOR_KEY = "openwa"
APP_SLUG_DEFAULT = "whatsapp"
_SAFE_SESSION_CHARS = re.compile(r"[^A-Za-z0-9-]+")


@dataclass(frozen=True, slots=True)
class OpenWAStatusMapping:
    provider_status: str
    connection_status: str
    health: ConnectionHealth
    ready: bool = False


def map_openwa_status(provider_status: str | None) -> OpenWAStatusMapping:
    raw = str(provider_status or "").strip() or "unknown"
    normalized = raw.lower()
    if normalized == OpenWASessionStatus.READY.value:
        return OpenWAStatusMapping(
            provider_status=raw,
            connection_status=ConnectionStatus.ACTIVE.value,
            health=ConnectionHealth.HEALTHY,
            ready=True,
        )
    if normalized in {
        OpenWASessionStatus.CREATED.value,
        OpenWASessionStatus.INITIALIZING.value,
        OpenWASessionStatus.QR_READY.value,
        OpenWASessionStatus.AUTHENTICATING.value,
    }:
        return OpenWAStatusMapping(
            provider_status=raw,
            connection_status=ConnectionStatus.CONNECTING.value,
            health=ConnectionHealth.UNKNOWN,
        )
    if normalized == OpenWASessionStatus.ACTION_REQUIRED.value:
        return OpenWAStatusMapping(
            provider_status=raw,
            connection_status=ConnectionStatus.ERROR.value,
            health=ConnectionHealth.DEGRADED,
        )
    if normalized == OpenWASessionStatus.DISCONNECTED.value:
        return OpenWAStatusMapping(
            provider_status=raw,
            connection_status=ConnectionStatus.DISCONNECTED.value,
            health=ConnectionHealth.DEGRADED,
        )
    if normalized == OpenWASessionStatus.FAILED.value:
        return OpenWAStatusMapping(
            provider_status=raw,
            connection_status=ConnectionStatus.ERROR.value,
            health=ConnectionHealth.FAILED,
        )
    return OpenWAStatusMapping(
        provider_status=raw,
        connection_status=ConnectionStatus.ERROR.value,
        health=ConnectionHealth.FAILED,
    )


class OpenWAChannelService:
    def __init__(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry | None = None,
        settings: Settings | None = None,
        client_factory: type[OpenWAClient] | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or connector_registry
        self.settings = settings or get_settings()
        self.catalog = AppCatalogRepository(db)
        self.access = AppAccessService(db)
        self.credentials = ConnectorCredentialService(db, settings=self.settings)
        self.connections = ConnectorConnectionService(db, registry=self.registry)
        self.experts = ExpertAccessService(db)
        self.client_factory = client_factory or OpenWAClient

    def start_session_connection(
        self,
        workspace: Workspace,
        role: str,
        actor_id: uuid.UUID,
        *,
        app_slug: str = APP_SLUG_DEFAULT,
        connection_id: uuid.UUID | None = None,
        connect_mode: str = "qr",
    ) -> WhatsAppConnectionOut:
        self._require_manage(role)
        self._require_registry_available()
        app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=True
        )

        base = self.connections.start_connection(
            workspace=workspace,
            role=role,
            actor_id=actor_id,
            app_slug=app_slug,
            connection_id=connection_id,
            auth_mode=ConnectorAuthMode.CUSTOM.value,
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=base.id,
            installation=installation,
            for_update=True,
        )

        creds = dict(self.credentials.get_credentials(row) or {})
        connect_mode = self._normalize_connect_mode(connect_mode)
        session_id = str(creds.get("session_id") or "").strip()
        session_name = str(creds.get("session_name") or "").strip()

        with self._client() as client:
            session: OpenWASession | None = None
            if session_id:
                session = self._try_get_session(client, session_id)
            if session is None:
                session_name = session_name or self._generate_session_name(workspace.slug)
                session = client.create_session(name=session_name)
                session_id = session.id
                session_name = session.name
            try:
                started = client.start_session(session_id)
            except AppError as exc:
                # Only treat "already started" / engine-loaded conflicts as recoverable.
                if not self._is_already_started_error(exc):
                    raise
                started = self._try_get_session(client, session_id) or session
                if started is None:
                    raise
            session_name = session_name or started.name

        next_creds = {
            "session_id": session_id,
            "session_name": session_name,
        }
        if creds.get("webhook_secret"):
            next_creds["webhook_secret"] = creds["webhook_secret"]
        # Preserve webhook_id / cleanup metadata across start.
        for key in ("webhook_id", "cleanup_pending"):
            if creds.get(key) is not None:
                next_creds[key] = creds[key]
        self.credentials.set_credentials(row, next_creds, merge_refresh=False)
        row.auth_mode = ConnectorAuthMode.CUSTOM.value
        row.connected_by_user_id = actor_id
        row.disconnected_at = None
        self._set_provider_metadata(
            row,
            provider_status=started.status,
            connect_mode=connect_mode,
        )
        self._clear_last_error(row)
        binding = self._ensure_channel_binding(row)
        # Keep Geem lifecycle aligned with OpenWA — do not leave ACTIVE+qr_ready.
        mapping = map_openwa_status(started.status)
        if mapping.ready:
            self._sync_connection_from_session(
                row=row, app_slug=app.slug, session=started
            )
        else:
            self._apply_non_ready_status(row, mapping=mapping, last_error=None)
        self.db.flush()
        return self._serialize_connection(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            binding=binding,
            can_manage=True,
        )

    def get_session_status(
        self,
        workspace: Workspace,
        role: str,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> WhatsAppConnectionOut:
        # Members may view status (read-only). Managers poll+sync while connecting.
        can_manage = can_manage_apps(role)
        app, installation = self._require_app_installation(
            workspace.id,
            app_slug=app_slug,
            require_active_access=can_manage,
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
            for_update=can_manage,
        )
        binding = self._ensure_channel_binding(row)
        if not can_manage:
            # Read-only snapshot — never mutate connection lifecycle as a member.
            return self._serialize_connection(
                row,
                app_slug=app.slug,
                connector_kind=app.connector_kind,
                binding=binding,
                can_manage=False,
            )

        session = self._fetch_current_session(row)
        try:
            self._sync_connection_from_session(
                row=row,
                app_slug=app.slug,
                session=session,
            )
        except AppError as exc:
            self._set_provider_metadata(
                row,
                provider_status=session.status,
                connect_mode=(row.extra or {}).get("connect_mode"),
            )
            row.health = ConnectionHealth.DEGRADED.value
            row.last_error_code = exc.category.value
            row.last_error_message = sanitize_error_message(exc.message)
            row.last_error_at = _now()
        self.db.flush()
        return self._serialize_connection(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            binding=binding,
            can_manage=True,
        )

    def get_qr(
        self,
        workspace: Workspace,
        role: str,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> OpenWAQrResponse:
        self._require_manage(role)
        _app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=True
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
        )
        session = self._fetch_current_session(row)
        if str(session.status).strip().lower() != OpenWASessionStatus.QR_READY.value:
            raise AppError(
                ErrorCategory.OPENWA_QR_NOT_READY,
                "WhatsApp QR code is not ready yet.",
                details={"provider_status": session.status},
            )
        with self._client() as client:
            return client.get_qr(self._session_id_from_row(row))

    def request_pairing_code(
        self,
        workspace: Workspace,
        role: str,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
        phone_number: str,
    ) -> dict[str, str]:
        self._require_manage(role)
        _app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=True
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
        )
        session = self._fetch_current_session(row)
        if str(session.status).strip().lower() != OpenWASessionStatus.QR_READY.value:
            raise AppError(
                ErrorCategory.OPENWA_QR_NOT_READY,
                "WhatsApp pairing requires the session to be QR-ready.",
                details={"provider_status": session.status},
            )
        normalized = normalize_whatsapp_phone(phone_number)
        with self._client() as client:
            code = client.request_pairing_code(
                self._session_id_from_row(row),
                phone_number=normalized,
            )
        return {"status": code.status, "pairing_code": code.pairingCode}

    def update_settings(
        self,
        workspace: Workspace,
        role: str,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
        expert_id: uuid.UUID | None | object = ...,
        auto_reply_enabled: bool | None = None,
        respond_to_groups: bool | None = None,
        enabled: bool | None = None,
    ) -> WhatsAppConnectionOut:
        self._require_manage(role)
        app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=True
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
            for_update=True,
        )
        binding = self._ensure_channel_binding(row)
        if expert_id is not ...:
            if expert_id is None:
                binding.expert_id = None
            else:
                assert isinstance(expert_id, uuid.UUID)
                try:
                    self.experts.resolve_for_workspace_consumer(
                        workspace=workspace,
                        expert_id=expert_id,
                        action=ExpertAction.USE,
                    )
                except AppError as exc:
                    raise AppError(
                        ErrorCategory.CHANNEL_EXPERT_INVALID,
                        "Selected Expert is not available for this workspace.",
                        details={"reason": exc.category.value},
                    ) from exc
                binding.expert_id = expert_id
        if auto_reply_enabled is not None:
            binding.auto_reply_enabled = auto_reply_enabled
        if respond_to_groups is not None:
            binding.respond_to_groups = respond_to_groups
        if enabled is not None:
            binding.enabled = enabled
        self.db.flush()
        return self._serialize_connection(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            binding=binding,
            can_manage=True,
        )

    def reconnect(
        self,
        workspace: Workspace,
        role: str,
        actor_id: uuid.UUID,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> WhatsAppConnectionOut:
        self._require_manage(role)
        app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=True
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
            for_update=True,
        )
        binding = self._ensure_channel_binding(row)
        if row.status not in {
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
            ConnectionStatus.ERROR.value,
            ConnectionStatus.DEGRADED.value,
        }:
            return self._serialize_connection(
                row,
                app_slug=app.slug,
                connector_kind=app.connector_kind,
                binding=binding,
                can_manage=True,
            )

        creds = dict(self.credentials.get_credentials(row) or {})
        session_id = str(creds.get("session_id") or "").strip()
        connect_mode = str((row.extra or {}).get("connect_mode") or "qr")
        if not session_id:
            return self.start_session_connection(
                workspace,
                role,
                actor_id,
                app_slug=app_slug,
                connection_id=connection_id,
                connect_mode=connect_mode,
            )

        with self._client() as client:
            session = self._try_get_session(client, session_id)
            if session is None:
                return self.start_session_connection(
                    workspace,
                    role,
                    actor_id,
                    app_slug=app_slug,
                    connection_id=connection_id,
                    connect_mode=connect_mode,
                )
            if not bool(session.engineLoaded):
                session = client.start_session(session_id)

        self._sync_connection_from_session(row=row, app_slug=app.slug, session=session)
        self.db.flush()
        return self._serialize_connection(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            binding=binding,
            can_manage=True,
        )

    def list_connections(
        self,
        *,
        workspace: Workspace,
        role: str,
        app_slug: str,
        limit: int = 50,
        offset: int = 0,
    ) -> AppConnectionListOut:
        can_manage = can_manage_apps(role)
        base = self.connections.list_connections(
            workspace=workspace,
            role=role,
            app_slug=app_slug,
            limit=limit,
            offset=offset,
        )
        if not base.items:
            return base
        enriched: list[WhatsAppConnectionOut] = []
        for item in base.items:
            row = self.db.get(AppConnection, item.id)
            if row is None or row.workspace_id != workspace.id:
                continue
            binding = self._ensure_channel_binding(row)
            enriched.append(
                self._serialize_connection(
                    row,
                    app_slug=app_slug,
                    connector_kind=item.connector_kind,
                    binding=binding,
                    can_manage=can_manage,
                )
            )
        self.db.flush()
        return AppConnectionListOut(
            items=enriched,  # type: ignore[arg-type]
            total=base.total,
            limit=base.limit,
            offset=base.offset,
            used=base.used,
            connection_limit=base.connection_limit,
        )

    def get_connection(
        self,
        *,
        workspace: Workspace,
        role: str,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> WhatsAppConnectionOut:
        can_manage = can_manage_apps(role)
        app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=False
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
        )
        binding = self._ensure_channel_binding(row)
        return self._serialize_connection(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            binding=binding,
            can_manage=can_manage,
        )

    def disconnect_whatsapp(
        self,
        workspace: Workspace,
        role: str,
        actor_id: uuid.UUID,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> WhatsAppConnectionOut:
        self._require_manage(role)
        app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=False
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
            for_update=True,
        )
        if row.status == ConnectionStatus.DISCONNECTED.value:
            raise AppError(
                ErrorCategory.CONNECTOR_ALREADY_DISCONNECTED,
                "Connection is already disconnected.",
            )

        binding = self._ensure_channel_binding(row)
        creds = dict(self.credentials.get_credentials(row) or {})
        sync_state = dict(self.credentials.get_sync_state(row) or {})
        if row.status != ConnectionStatus.DISCONNECTED.value:
            _transition(row, ConnectionStatus.DISCONNECTED.value)
        row.disconnected_at = _now()
        row.health = ConnectionHealth.UNKNOWN.value
        self._set_provider_metadata(row, provider_status="disconnected")
        self._clear_last_error(row)
        # Fail closed for inbound first, then attempt provider teardown.
        self.db.flush()

        cleanup_ok = self._best_effort_provider_disconnect(
            creds=creds, sync_state=sync_state
        )
        if cleanup_ok:
            self.credentials.clear_all_secrets(row)
            meta = dict(row.extra or {})
            meta.pop("cleanup_pending", None)
            row.extra = meta
        else:
            # Keep session identifiers so cleanup can be retried later.
            pending = {
                "session_id": creds.get("session_id"),
                "session_name": creds.get("session_name"),
                "webhook_id": sync_state.get("webhook_id") or creds.get("webhook_id"),
                "cleanup_pending": True,
            }
            self.credentials.set_credentials(row, pending, merge_refresh=False)
            self.credentials.set_sync_state(
                row,
                {
                    **{k: v for k, v in sync_state.items() if k != "webhook_secret"},
                    "cleanup_pending": True,
                },
            )
            meta = dict(row.extra or {})
            meta["cleanup_pending"] = True
            row.extra = meta
            row.last_error_code = ErrorCategory.OPENWA_UNAVAILABLE.value
            row.last_error_message = sanitize_error_message(
                "WhatsApp disconnected locally; remote cleanup is pending retry."
            )
            row.last_error_at = _now()
        self.db.flush()
        _ = actor_id
        return self._serialize_connection(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            binding=binding,
            can_manage=True,
        )

    def delete_whatsapp_connection(
        self,
        workspace: Workspace,
        role: str,
        actor_id: uuid.UUID,
        *,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> None:
        """Permanently remove a disconnected/revoked WhatsApp connection.

        Tears down the OpenWA session (best-effort when already gone), then
        hard-deletes the Geem ``app_connection`` row and related records.
        """
        self._require_manage(role)
        app, installation = self._require_app_installation(
            workspace.id, app_slug=app_slug, require_active_access=False
        )
        row = self._require_connection_row(
            workspace_id=workspace.id,
            connection_id=connection_id,
            installation=installation,
            for_update=True,
        )
        if row.status not in {
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
        }:
            raise AppError(
                ErrorCategory.CONNECTOR_INVALID_TRANSITION,
                "Only disconnected WhatsApp connections can be deleted. Disconnect first.",
            )

        creds = dict(self.credentials.get_credentials(row) or {})
        sync_state = dict(self.credentials.get_sync_state(row) or {})
        cleanup_ok = self._best_effort_provider_disconnect(
            creds=creds, sync_state=sync_state
        )
        if not cleanup_ok:
            raise AppError(
                ErrorCategory.OPENWA_UNAVAILABLE,
                "Could not delete the OpenWA session. Try again shortly.",
            )

        self.repo.purge_connection(row)
        _ = (actor_id, app)
        logger.info(
            "openwa_connection_deleted",
            extra={
                "workspace_id": str(workspace.id),
                "connection_id": str(connection_id),
            },
        )

    def ensure_webhook_registered(self, connection: AppConnection) -> str:
        creds = dict(self.credentials.get_credentials(connection) or {})
        session_id = str(creds.get("session_id") or "").strip()
        if not session_id:
            raise AppError(
                ErrorCategory.CONNECTOR_CREDENTIALS_INVALID,
                "Connection credentials are missing an OpenWA session id.",
            )
        routing_encrypted = connection.webhook_routing_token_encrypted
        if not routing_encrypted:
            raise AppError(
                ErrorCategory.OPENWA_WEBHOOK_FAILED,
                "Webhook routing token is unavailable for this connection.",
            )
        token = decrypt_secret(routing_encrypted, settings=self.settings)
        base = (self.settings.app_url or "").rstrip("/")
        if not base:
            raise AppError(
                ErrorCategory.OPENWA_WEBHOOK_FAILED,
                "APP_URL must be configured before registering the WhatsApp webhook.",
            )
        url = f"{base}/api/connectors/webhooks/{CONNECTOR_KEY}/{token}"
        secret = str(creds.get("webhook_secret") or "").strip() or secrets.token_urlsafe(32)
        sync_state = dict(self.credentials.get_sync_state(connection) or {})
        stored_webhook_id = str(sync_state.get("webhook_id") or "").strip()

        with self._client() as client:
            existing = client.list_webhooks(session_id)
            chosen = None
            if stored_webhook_id:
                chosen = next((item for item in existing if item.id == stored_webhook_id), None)
            if chosen is None:
                chosen = next((item for item in existing if item.url == url), None)
            if chosen is not None:
                webhook = client.update_webhook(
                    session_id,
                    chosen.id,
                    url=url,
                    secret=secret,
                    events=list(OPENWA_WEBHOOK_EVENTS),
                    active=True,
                )
            else:
                webhook = client.register_webhook(
                    session_id,
                    url=url,
                    secret=secret,
                    events=list(OPENWA_WEBHOOK_EVENTS),
                )

        creds["webhook_secret"] = secret
        sync_state["webhook_id"] = webhook.id
        sync_state["webhook_url"] = webhook.url
        self.credentials.set_credentials(connection, creds, merge_refresh=False)
        self.credentials.set_sync_state(connection, sync_state)
        self.db.flush()
        return webhook.id

    def ensure_webhook_removed(self, connection: AppConnection) -> None:
        """Best-effort delete OpenWA webhook(s). Keeps the linked session intact."""
        if connection.connector_key != CONNECTOR_KEY:
            return
        creds = dict(self.credentials.get_credentials(connection) or {})
        session_id = str(creds.get("session_id") or "").strip()
        sync_state = dict(self.credentials.get_sync_state(connection) or {})
        webhook_id = str(sync_state.get("webhook_id") or "").strip()
        webhook_url = str(sync_state.get("webhook_url") or "").strip()

        if session_id:
            try:
                with self._client() as client:
                    if webhook_id:
                        try:
                            client.delete_webhook(session_id, webhook_id)
                        except Exception:
                            logger.info(
                                "openwa_webhook_delete_failed",
                                extra={
                                    "connection_id": str(connection.id),
                                    "webhook_id": webhook_id,
                                },
                            )
                    else:
                        try:
                            existing = client.list_webhooks(session_id)
                        except Exception:
                            existing = []
                        for item in existing:
                            if webhook_url and item.url != webhook_url:
                                continue
                            try:
                                client.delete_webhook(session_id, item.id)
                            except Exception:
                                logger.info(
                                    "openwa_webhook_delete_failed",
                                    extra={
                                        "connection_id": str(connection.id),
                                        "webhook_id": item.id,
                                    },
                                )
            except Exception:
                logger.info(
                    "openwa_webhook_remove_unavailable",
                    extra={"connection_id": str(connection.id)},
                )

        if "webhook_id" in sync_state or "webhook_url" in sync_state:
            sync_state.pop("webhook_id", None)
            sync_state.pop("webhook_url", None)
            self.credentials.set_sync_state(connection, sync_state)
            self.db.flush()

    def register_webhooks_for_installation(
        self,
        *,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
        app_slug: str | None = None,
    ) -> None:
        """Register webhooks for ready OpenWA sessions under an active installation."""
        if not self.registry.is_available(CONNECTOR_KEY):
            return
        slug = (app_slug or APP_SLUG_DEFAULT).strip() or APP_SLUG_DEFAULT
        try:
            self.access.require_active(workspace_id, app_slug=slug)
        except AppError:
            return

        rows, _ = self.repo.list_connections(
            workspace_id,
            app_installation_id=installation_id,
            connector_key=CONNECTOR_KEY,
            limit=200,
            offset=0,
        )
        for row in rows:
            if row.status in {
                ConnectionStatus.DISCONNECTED.value,
                ConnectionStatus.REVOKED.value,
            }:
                continue
            try:
                session = self._fetch_current_session(row)
            except AppError:
                continue
            if not map_openwa_status(session.status).ready:
                continue
            try:
                self.ensure_webhook_registered(row)
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "openwa_webhook_register_on_install_failed",
                    extra={
                        "workspace_id": str(workspace_id),
                        "connection_id": str(row.id),
                        "error": sanitize_error_message(str(exc)),
                    },
                )

    def remove_webhooks_for_installation(
        self,
        *,
        workspace_id: uuid.UUID,
        installation_id: uuid.UUID,
    ) -> None:
        """Best-effort webhook teardown for all OpenWA connections under an installation."""
        rows, _ = self.repo.list_connections(
            workspace_id,
            app_installation_id=installation_id,
            connector_key=CONNECTOR_KEY,
            limit=200,
            offset=0,
        )
        for row in rows:
            self.ensure_webhook_removed(row)

    def sync_session_event(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        provider_status: str | None,
        last_error: str | None = None,
    ) -> None:
        row = self.repo.get_connection(workspace_id, connection_id, for_update=True)
        if row is None or row.connector_key != CONNECTOR_KEY:
            return
        app = self._app_for_connection(row)
        session = None
        try:
            session = self._fetch_current_session(row)
        except AppError as exc:
            if exc.category != ErrorCategory.OPENWA_SESSION_NOT_FOUND:
                raise
        if session is not None:
            self._sync_connection_from_session(row=row, app_slug=app.slug, session=session)
            return
        mapping = map_openwa_status(provider_status)
        self._set_provider_metadata(row, provider_status=mapping.provider_status)
        self._apply_non_ready_status(
            row,
            mapping=mapping,
            last_error=last_error or "OpenWA session is unavailable.",
        )

    @property
    def repo(self):  # type: ignore[override]
        return self.connections.repo

    def _require_manage(self, role: str) -> None:
        if not can_manage_apps(role):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Only owners and admins can manage WhatsApp connections.",
            )

    def _require_registry_available(self) -> None:
        if not self.registry.is_available(CONNECTOR_KEY):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "OpenWA connector is not available.",
                details={"connector_key": CONNECTOR_KEY},
            )

    def _client(self) -> OpenWAClient:
        return self.client_factory(settings=self.settings)

    @staticmethod
    def _normalize_connect_mode(connect_mode: str | None) -> str:
        mode = str(connect_mode or "qr").strip().lower()
        if mode not in {"qr", "pairing"}:
            raise AppError(
                ErrorCategory.VALIDATION,
                "connect_mode must be 'qr' or 'pairing'.",
            )
        return mode

    def _require_app_installation(
        self,
        workspace_id: uuid.UUID,
        *,
        app_slug: str,
        require_active_access: bool,
    ) -> tuple[CatalogApp, AppInstallation]:
        app = self.catalog.get_app_by_slug(app_slug)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        if app.connector_key != CONNECTOR_KEY:
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_SUPPORTED,
                "This app does not use the OpenWA connector.",
            )
        installation = self.catalog.get_installation_by_app(workspace_id, app.id)
        if (
            installation is None
            or installation.workspace_id != workspace_id
            or installation.status != AppInstallationStatus.ACTIVE.value
        ):
            raise AppError(
                ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
                "App must be installed before connecting.",
            )
        if require_active_access:
            self.access.require_active(workspace_id, app_slug=app_slug)
        return app, installation

    def _require_connection_row(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        installation: AppInstallation,
        for_update: bool = False,
    ) -> AppConnection:
        row = self.repo.get_connection(workspace_id, connection_id, for_update=for_update)
        if row is None or row.app_installation_id != installation.id:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        if row.connector_key != CONNECTOR_KEY:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        return row

    def _ensure_channel_binding(self, connection: AppConnection) -> ChannelBinding:
        binding = self.db.scalar(
            select(ChannelBinding).where(
                ChannelBinding.workspace_id == connection.workspace_id,
                ChannelBinding.app_connection_id == connection.id,
            )
        )
        if binding is not None:
            return binding
        binding = ChannelBinding(
            workspace_id=connection.workspace_id,
            app_connection_id=connection.id,
            expert_id=None,
            enabled=True,
            auto_reply_enabled=True,
            respond_to_groups=False,
        )
        self.db.add(binding)
        self.db.flush()
        return binding

    def _fetch_current_session(self, row: AppConnection) -> OpenWASession:
        session_id = self._session_id_from_row(row)
        with self._client() as client:
            return client.get_session(session_id)

    def _try_get_session(
        self,
        client: OpenWAClient,
        session_id: str,
    ) -> OpenWASession | None:
        try:
            return client.get_session(session_id)
        except AppError as exc:
            if exc.category == ErrorCategory.OPENWA_SESSION_NOT_FOUND:
                return None
            raise

    def _session_id_from_row(self, row: AppConnection) -> str:
        creds = self.credentials.get_credentials(row) or {}
        session_id = str(creds.get("session_id") or "").strip()
        if not session_id:
            raise AppError(
                ErrorCategory.CONNECTOR_CREDENTIALS_INVALID,
                "Connection credentials are missing an OpenWA session id.",
            )
        return session_id

    def _sync_connection_from_session(
        self,
        *,
        row: AppConnection,
        app_slug: str,
        session: OpenWASession,
    ) -> None:
        mapping = map_openwa_status(session.status)
        connect_mode = str((row.extra or {}).get("connect_mode") or "qr")
        self._set_provider_metadata(
            row,
            provider_status=mapping.provider_status,
            connect_mode=connect_mode,
        )
        self._apply_session_identity(row, session)
        if mapping.ready:
            # Never re-register/activate a locally disconnected/revoked connection.
            if row.status in {
                ConnectionStatus.DISCONNECTED.value,
                ConnectionStatus.REVOKED.value,
            }:
                row.health = ConnectionHealth.UNKNOWN.value
                return
            access_ok = True
            try:
                self.access.require_active(row.workspace_id, app_slug=app_slug)
            except AppError:
                access_ok = False
                self.ensure_webhook_removed(row)
            if access_ok:
                self.ensure_webhook_registered(row)
            creds = self.credentials.get_credentials(row) or {}
            if row.status == ConnectionStatus.ACTIVE.value:
                self.connections.mark_healthy(row)
                row.last_success_at = _now()
            else:
                self.connections.activate_connection(
                    workspace_id=row.workspace_id,
                    connection_id=row.id,
                    credentials=creds,
                    actor_id=row.connected_by_user_id,
                    external_account_id=row.external_account_id,
                    external_account_name=row.external_account_name,
                    display_name=row.display_name,
                )
            self._clear_last_error(row)
            return
        last_error = sanitize_error_message(session.lastError) if session.lastError else None
        self._apply_non_ready_status(row, mapping=mapping, last_error=last_error)

    def _apply_non_ready_status(
        self,
        row: AppConnection,
        *,
        mapping: OpenWAStatusMapping,
        last_error: str | None,
    ) -> None:
        if row.status in {
            ConnectionStatus.DISCONNECTED.value,
            ConnectionStatus.REVOKED.value,
        }:
            row.health = ConnectionHealth.UNKNOWN.value
            return
        if row.status != mapping.connection_status:
            _transition(row, mapping.connection_status)
        row.health = mapping.health.value
        if mapping.connection_status == ConnectionStatus.CONNECTING.value:
            self._clear_last_error(row)
            return
        row.last_error_code = ErrorCategory.CONNECTOR_CONNECTION_FAILED.value
        row.last_error_message = last_error or (
            f"OpenWA session status is {mapping.provider_status}."
        )
        row.last_error_at = _now()

    @staticmethod
    def _apply_session_identity(row: AppConnection, session: OpenWASession) -> None:
        phone = str(session.phone or "").strip() or None
        push_name = str(session.pushName or "").strip() or None
        if phone is not None:
            row.external_account_id = phone
        if push_name is not None:
            row.external_account_name = push_name
            row.display_name = push_name
        elif phone and not row.display_name:
            row.display_name = phone

    @staticmethod
    def _set_provider_metadata(
        row: AppConnection,
        *,
        provider_status: str | None,
        connect_mode: str | None = None,
    ) -> None:
        meta = dict(row.extra or {})
        if provider_status is not None:
            meta["provider_status"] = str(provider_status)
        if connect_mode is not None:
            meta["connect_mode"] = str(connect_mode)
        row.extra = meta

    @staticmethod
    def _clear_last_error(row: AppConnection) -> None:
        row.last_error_code = None
        row.last_error_message = None
        row.last_error_at = None

    def _serialize_connection(
        self,
        row: AppConnection,
        *,
        app_slug: str,
        connector_kind: str | None,
        binding: ChannelBinding,
        can_manage: bool,
    ) -> WhatsAppConnectionOut:
        base = to_connection_out(
            row,
            app_slug=app_slug,
            connector_kind=connector_kind,
            can_manage=can_manage,
            adapter_available=self.registry.is_available(CONNECTOR_KEY),
            supports_sync=False,
        )
        return WhatsAppConnectionOut.model_validate(
            {
                **base.model_dump(),
                "provider_status": (row.extra or {}).get("provider_status"),
                "connect_mode": (row.extra or {}).get("connect_mode"),
                "phone": row.external_account_id,
                "expert_id": binding.expert_id,
                "enabled": bool(binding.enabled),
                "auto_reply_enabled": bool(binding.auto_reply_enabled),
                "respond_to_groups": bool(binding.respond_to_groups),
            }
        )

    def _best_effort_provider_disconnect(
        self,
        *,
        creds: dict[str, object],
        sync_state: dict[str, object],
    ) -> bool:
        """Return True when remote teardown completed (or nothing to tear down)."""
        session_id = str(creds.get("session_id") or "").strip()
        if not session_id:
            return True
        webhook_id = str(
            sync_state.get("webhook_id") or creds.get("webhook_id") or ""
        ).strip()
        try:
            with self._client() as client:
                if webhook_id:
                    try:
                        client.delete_webhook(session_id, webhook_id)
                    except AppError:
                        pass
                try:
                    client.logout_session(session_id)
                except AppError:
                    pass
                try:
                    client.delete_session(session_id)
                except AppError as exc:
                    if exc.category != ErrorCategory.OPENWA_SESSION_NOT_FOUND:
                        return False
            return True
        except Exception:
            return False

    @staticmethod
    def _is_already_started_error(exc: AppError) -> bool:
        """True only for recoverable 'engine already running' start conflicts."""
        if exc.category != ErrorCategory.OPENWA_REQUEST_INVALID:
            return False
        details = exc.details or {}
        provider_code = str(details.get("provider_code") or "").upper()
        message = str(exc.message or "").lower()
        if provider_code in {"SESSION_ALREADY_STARTED", "ENGINE_ALREADY_RUNNING"}:
            return True
        needles = (
            "already started",
            "already running",
            "session already",
            "engine already",
        )
        return any(n in message for n in needles)

    def _generate_session_name(self, workspace_slug: str) -> str:
        safe_slug = _SAFE_SESSION_CHARS.sub("-", (workspace_slug or "").strip())
        safe_slug = safe_slug.strip("-") or "workspace"
        suffix = secrets.token_hex(3)
        max_slug_len = max(1, 50 - len("geem--") - len(suffix))
        safe_slug = safe_slug[:max_slug_len].strip("-") or "workspace"
        name = f"geem-{safe_slug}-{suffix}"
        return name[:50]

    def _app_for_connection(self, connection: AppConnection) -> CatalogApp:
        installation = self.catalog.get_installation_by_id(connection.app_installation_id)
        if installation is None:
            raise AppError(
                ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
                "App installation is not active.",
            )
        app = self.catalog.get_app_by_id(installation.app_id)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        return app
