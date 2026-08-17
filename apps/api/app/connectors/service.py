"""App connection lifecycle service (Phase 9C).

Gates on AppAccessService; never duplicates billing rules.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.entitlements import AppEntitlementService
from app.apps_catalog.models import (
    AppInstallation,
    AppInstallationStatus,
    CatalogApp,
)
from app.apps_catalog.policy import can_manage_apps
from app.apps_catalog.repository import AppCatalogRepository
from app.common.crypto import decrypt_secret, encrypt_secret
from app.common.security_log import security_log
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.locks import workspace_app_connection_lock
from app.connectors.models import AppConnection
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.repository import (
    ConnectorRepository,
    generate_routing_token,
    hash_routing_token,
)
from app.connectors.sanitize import sanitize_error_message
from app.connectors.schemas import (
    AppConnectionListOut,
    AppConnectionOut,
    ConnectorCapabilityOut,
    to_connection_out,
)
from app.connectors.types import (
    CONNECTION_LIMIT_STATUSES,
    CONNECTION_TRANSITIONS,
    CONNECTION_USABLE_STATUSES,
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
)
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory, raise_resource_quota
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)

CONNECTIONS_ENTITLEMENT_KEY = "connections"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _transition(connection: AppConnection, new_status: str) -> None:
    allowed = CONNECTION_TRANSITIONS.get(connection.status, frozenset())
    if new_status not in allowed and new_status != connection.status:
        raise AppError(
            ErrorCategory.CONNECTOR_INVALID_TRANSITION,
            f"Cannot transition connection from {connection.status} to {new_status}.",
            details={"from": connection.status, "to": new_status},
        )
    connection.status = new_status


class ConnectorConnectionService:
    def __init__(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry | None = None,
    ) -> None:
        self.db = db
        self.repo = ConnectorRepository(db)
        self.catalog = AppCatalogRepository(db)
        self.access = AppAccessService(db)
        self.entitlements = AppEntitlementService(db)
        self.credentials = ConnectorCredentialService(db)
        self.registry = registry or connector_registry
        self.settings = get_settings()

    def connector_capability_for_app(self, app: CatalogApp) -> ConnectorCapabilityOut | None:
        if not app.connector_key:
            return None
        desc = self.registry.describe(app.connector_key)
        if desc is None:
            return None
        kind = app.connector_kind or desc.get("kind")
        return ConnectorCapabilityOut(
            key=app.connector_key,
            kind=kind,
            available=bool(desc.get("available")),
            auth_mode=desc.get("auth_mode"),
            can_connect=bool(desc.get("can_connect") and desc.get("available")),
            supports_sync=bool(desc.get("supports_sync")),
            supports_webhooks=bool(desc.get("supports_webhooks")),
            supports_health_check=bool(desc.get("supports_health_check")),
            unavailable_reason=desc.get("unavailable_reason"),
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
        app, installation = self._require_app_and_installation(
            workspace.id, app_slug, require_active_access=False
        )
        rows, total = self.repo.list_connections(
            workspace.id,
            app_installation_id=installation.id if installation else None,
            connector_key=app.connector_key,
            limit=limit,
            offset=offset,
        )
        # If not installed, return empty list (still 200 for browse).
        if installation is None or installation.status != AppInstallationStatus.ACTIVE.value:
            return AppConnectionListOut(items=[], total=0, limit=limit, offset=offset)

        items = [
            to_connection_out(
                row,
                app_slug=app.slug,
                connector_kind=app.connector_kind,
                can_manage=can_manage,
                adapter_available=self.registry.is_available(row.connector_key),
                supports_sync=self._supports_sync(row.connector_key),
            )
            for row in rows
        ]
        return AppConnectionListOut(items=items, total=total, limit=limit, offset=offset)

    def get_connection(
        self,
        *,
        workspace: Workspace,
        role: str,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> AppConnectionOut:
        can_manage = can_manage_apps(role)
        app, installation = self._require_app_and_installation(
            workspace.id, app_slug, require_active_access=False
        )
        if (
            installation is None
            or installation.status != AppInstallationStatus.ACTIVE.value
        ):
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        row = self.repo.get_connection(workspace.id, connection_id)
        if (
            row is None
            or row.app_installation_id != installation.id
            or (app.connector_key and row.connector_key != app.connector_key)
        ):
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        return to_connection_out(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            can_manage=can_manage,
            adapter_available=self.registry.is_available(row.connector_key),
            supports_sync=self._supports_sync(row.connector_key),
        )

    def start_connection(
        self,
        *,
        workspace: Workspace,
        role: str,
        actor_id: uuid.UUID,
        app_slug: str,
        display_name: str | None = None,
        auth_mode: str | None = None,
        connection_id: uuid.UUID | None = None,
        return_path: str | None = None,
    ) -> AppConnectionOut:
        """Create or reopen a connection in ``connecting`` (requires registered adapter)."""
        if not can_manage_apps(role):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Only owners and admins can manage connections.",
            )
        app, installation = self._require_app_and_installation(
            workspace.id, app_slug, require_active_access=True
        )
        assert installation is not None
        if not app.connector_key:
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_SUPPORTED,
                "This app does not support external connections.",
            )
        if not self.registry.is_available(app.connector_key):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "Connector adapter is not available yet.",
                details={"connector_key": app.connector_key},
            )
        adapter = self.registry.get(app.connector_key)
        mode = auth_mode or (
            adapter.auth_mode.value
            if isinstance(adapter.auth_mode, ConnectorAuthMode)
            else str(adapter.auth_mode)
        )

        workspace_app_connection_lock(self.db, workspace.id, app.id)

        row: AppConnection
        reconnect = False
        # Reconnect existing disconnected/revoked row.
        if connection_id is not None:
            existing = self.repo.get_connection(
                workspace.id, connection_id, for_update=True
            )
            if existing is None or existing.app_installation_id != installation.id:
                raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
            # Reconnecting into a limit-counted status must respect the entitlement.
            if existing.status not in CONNECTION_LIMIT_STATUSES:
                used = self.repo.count_limit_connections(
                    workspace.id, app_installation_id=installation.id
                )
                limit = self._connection_limit(workspace.id, app_slug)
                if used >= limit:
                    raise_resource_quota(
                        ErrorCategory.CONNECTOR_LIMIT_REACHED,
                        "Connection limit reached for this app.",
                        metric=CONNECTIONS_ENTITLEMENT_KEY,
                        limit=limit,
                        used=used,
                        remaining=0,
                    )
            _transition(existing, ConnectionStatus.CONNECTING.value)
            existing.disconnected_at = None
            existing.health = ConnectionHealth.UNKNOWN.value
            existing.last_error_code = None
            existing.last_error_message = None
            if display_name:
                existing.display_name = display_name
            existing.auth_mode = mode
            self._ensure_routing_token(existing)
            self.db.flush()
            security_log(
                "app.connection.reconnected",
                workspace_id=str(workspace.id),
                actor_id=str(actor_id),
                app_id=str(app.id),
                installation_id=str(installation.id),
                connection_id=str(existing.id),
            )
            logger.info(
                "connector_connection_started",
                extra={
                    "workspace_id": str(workspace.id),
                    "connection_id": str(existing.id),
                    "reconnect": True,
                },
            )
            row = existing
            reconnect = True
        else:
            used = self.repo.count_limit_connections(
                workspace.id, app_installation_id=installation.id
            )
            limit = self._connection_limit(workspace.id, app_slug)
            if used >= limit:
                raise_resource_quota(
                    ErrorCategory.CONNECTOR_LIMIT_REACHED,
                    "Connection limit reached for this app.",
                    metric=CONNECTIONS_ENTITLEMENT_KEY,
                    limit=limit,
                    used=used,
                    remaining=0,
                )

            row = AppConnection(
                workspace_id=workspace.id,
                app_installation_id=installation.id,
                connector_key=app.connector_key,
                display_name=display_name,
                auth_mode=mode,
                status=ConnectionStatus.CONNECTING.value,
                health=ConnectionHealth.UNKNOWN.value,
                connected_by_user_id=actor_id,
                extra={},
            )
            self._ensure_routing_token(row)
            self.repo.add_connection(row)
            security_log(
                "app.connection.started",
                workspace_id=str(workspace.id),
                actor_id=str(actor_id),
                app_id=str(app.id),
                installation_id=str(installation.id),
                connection_id=str(row.id),
            )
            logger.info(
                "connector_connection_started",
                extra={"workspace_id": str(workspace.id), "connection_id": str(row.id)},
            )

        authorization_url: str | None = None
        if (
            mode == ConnectorAuthMode.OAUTH2.value
            and self.registry.is_available(row.connector_key)
            and hasattr(adapter, "build_authorization_request")
        ):
            from app.connectors.oauth_state import ConnectorOAuthStateService
            import base64
            import hashlib

            oauth = ConnectorOAuthStateService(settings=self.settings)
            state_payload = oauth.create(
                workspace_id=workspace.id,
                actor_id=actor_id,
                app_installation_id=installation.id,
                connector_key=row.connector_key,
                connection_id=row.id,
                return_path=return_path,
                include_pkce=True,
            )
            challenge = None
            method = None
            if state_payload.code_verifier:
                digest = hashlib.sha256(
                    state_payload.code_verifier.encode("ascii")
                ).digest()
                challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
                method = "S256"
            from app.connectors.oauth_redirect import effective_oauth_redirect_uri

            redirect_uri = effective_oauth_redirect_uri(
                self.settings, row.connector_key
            )
            try:
                auth_req = adapter.build_authorization_request(  # type: ignore[attr-defined]
                    state=state_payload.state,
                    redirect_uri=redirect_uri,
                    code_challenge=challenge,
                    code_challenge_method=method,
                    reconnect=reconnect,
                )
            except TypeError:
                auth_req = adapter.build_authorization_request(  # type: ignore[attr-defined]
                    state=state_payload.state,
                    redirect_uri=redirect_uri,
                    code_challenge=challenge,
                    code_challenge_method=method,
                )
            authorization_url = auth_req.authorization_url

        return to_connection_out(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            can_manage=True,
            adapter_available=True,
            supports_sync=self._supports_sync(row.connector_key),
            authorization_url=authorization_url,
        )

    def activate_connection(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        actor_id: uuid.UUID | None = None,
        external_account_id: str | None = None,
        external_account_name: str | None = None,
        display_name: str | None = None,
        credentials_expires_at: datetime | None = None,
    ) -> AppConnection:
        """Mark connection active after successful auth (internal / adapter completion)."""
        row = self.repo.get_connection(workspace_id, connection_id, for_update=True)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        installation = self.catalog.get_installation_by_id(row.app_installation_id)
        if installation is None or installation.workspace_id != workspace_id:
            raise AppError(
                ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
                "Installation not found for connection.",
            )
        app = self.catalog.get_app_by_id(installation.app_id)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        self.access.require_active(workspace_id, app_slug=app.slug)

        self.credentials.set_credentials(
            row, credentials, expires_at=credentials_expires_at, merge_refresh=True
        )
        # Seed provider-neutral sync_state with drive identity when present.
        drive_id = credentials.get("drive_id")
        if drive_id:
            existing_state = self.credentials.get_sync_state(row) or {}
            seeded = {
                **existing_state,
                "drive_id": drive_id,
                "drive_type": credentials.get("drive_type"),
                "drive_web_url": credentials.get("drive_web_url"),
            }
            self.credentials.set_sync_state(row, seeded)
        if external_account_id is not None:
            row.external_account_id = external_account_id
        if external_account_name is not None:
            row.external_account_name = external_account_name
        if display_name is not None:
            row.display_name = display_name
        _transition(row, ConnectionStatus.ACTIVE.value)
        row.health = ConnectionHealth.HEALTHY.value
        row.connected_at = _now()
        row.disconnected_at = None
        row.last_success_at = _now()
        row.last_error_code = None
        row.last_error_message = None
        if actor_id is not None:
            row.connected_by_user_id = actor_id
        self.db.flush()
        security_log(
            "app.connection.connected",
            workspace_id=str(workspace_id),
            actor_id=str(actor_id) if actor_id else None,
            app_id=str(app.id),
            installation_id=str(installation.id),
            connection_id=str(row.id),
        )
        logger.info(
            "connector_connection_activated",
            extra={"workspace_id": str(workspace_id), "connection_id": str(row.id)},
        )
        return row

    def disconnect(
        self,
        *,
        workspace: Workspace,
        role: str,
        actor_id: uuid.UUID,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> AppConnectionOut:
        if not can_manage_apps(role):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Only owners and admins can disconnect connections.",
            )
        app, installation = self._require_app_and_installation(
            workspace.id, app_slug, require_active_access=False
        )
        row = self.repo.get_connection(workspace.id, connection_id, for_update=True)
        if row is None or (installation and row.app_installation_id != installation.id):
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        if row.status == ConnectionStatus.DISCONNECTED.value:
            raise AppError(
                ErrorCategory.CONNECTOR_ALREADY_DISCONNECTED,
                "Connection is already disconnected.",
            )

        # Best-effort provider disconnect (may no-op when adapter unavailable).
        adapter = self.registry.try_get(row.connector_key)
        creds = self.credentials.get_credentials(row)
        sync_state = self.credentials.get_sync_state(row)
        if adapter is not None:
            try:
                try:
                    adapter.disconnect(
                        credentials=creds,
                        connection_id=row.id,
                        workspace_id=workspace.id,
                        sync_state=sync_state,
                    )
                except TypeError:
                    adapter.disconnect(
                        credentials=creds,
                        connection_id=row.id,
                        workspace_id=workspace.id,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "connector_provider_disconnect_failed",
                    extra={
                        "connection_id": str(row.id),
                        "error": sanitize_error_message(str(exc)),
                    },
                )

        # Mark ExpertSources unavailable before clearing secrets.
        try:
            from app.experts.connector_sources import ExpertConnectorSourceService

            ExpertConnectorSourceService(self.db).mark_sources_unavailable_for_connection(
                workspace_id=workspace.id,
                connection_id=row.id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "connector_mark_sources_unavailable_failed",
                extra={
                    "connection_id": str(row.id),
                    "error": sanitize_error_message(str(exc)),
                },
            )

        self.credentials.clear_all_secrets(row)
        _transition(row, ConnectionStatus.DISCONNECTED.value)
        row.disconnected_at = _now()
        row.health = ConnectionHealth.UNKNOWN.value
        self.db.flush()
        security_log(
            "app.connection.disconnected",
            workspace_id=str(workspace.id),
            actor_id=str(actor_id),
            app_id=str(app.id),
            installation_id=str(row.app_installation_id),
            connection_id=str(row.id),
        )
        logger.info(
            "connector_connection_disconnected",
            extra={"workspace_id": str(workspace.id), "connection_id": str(row.id)},
        )
        return to_connection_out(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            can_manage=True,
            adapter_available=self.registry.is_available(row.connector_key),
            supports_sync=self._supports_sync(row.connector_key),
        )

    def require_usable_connection(
        self,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        app_slug: str | None = None,
    ) -> tuple[AppConnection, CatalogApp, AppInstallation]:
        row = self.repo.get_connection(workspace_id, connection_id)
        if row is None:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        installation = self.catalog.get_installation_by_id(row.app_installation_id)
        if (
            installation is None
            or installation.workspace_id != workspace_id
            or installation.status != AppInstallationStatus.ACTIVE.value
        ):
            raise AppError(
                ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
                "App installation is not active.",
            )
        app = self.catalog.get_app_by_id(installation.app_id)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        if app_slug and app.slug != app_slug:
            raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")
        self.access.require_active(workspace_id, app_slug=app.slug)
        if row.status not in CONNECTION_USABLE_STATUSES:
            if row.status == ConnectionStatus.DISCONNECTED.value:
                raise AppError(
                    ErrorCategory.CONNECTOR_ALREADY_DISCONNECTED,
                    "Connection is disconnected.",
                )
            raise AppError(
                ErrorCategory.CONNECTOR_CONNECTION_FAILED,
                "Connection is not usable.",
                details={"status": row.status},
            )
        return row, app, installation

    def mark_authorization_failed(
        self,
        *,
        workspace_id: uuid.UUID,
        connection_id: uuid.UUID,
        error_code: str,
        error_message: str | None = None,
    ) -> AppConnection | None:
        """Persist OAuth failure so the connection leaves ``connecting``."""
        row = self.repo.get_connection(workspace_id, connection_id, for_update=True)
        if row is None:
            return None
        self.record_error(
            row,
            error_code=error_code,
            error_message=error_message or "Authorization failed.",
        )
        logger.info(
            "connector_authorization_failed",
            extra={
                "workspace_id": str(workspace_id),
                "connection_id": str(connection_id),
                "error_code": error_code,
            },
        )
        return row

    def record_error(
        self,
        connection: AppConnection,
        *,
        error_code: str,
        error_message: str | None,
        degrade: bool = False,
        revoke: bool = False,
    ) -> None:
        connection.last_error_code = error_code
        connection.last_error_message = sanitize_error_message(error_message)
        connection.last_error_at = _now()
        if revoke:
            _transition(connection, ConnectionStatus.REVOKED.value)
            self.credentials.clear_all_secrets(connection)
            connection.health = ConnectionHealth.FAILED.value
        elif degrade:
            if connection.status == ConnectionStatus.ACTIVE.value:
                _transition(connection, ConnectionStatus.DEGRADED.value)
            connection.health = ConnectionHealth.DEGRADED.value
        else:
            if connection.status in {
                ConnectionStatus.ACTIVE.value,
                ConnectionStatus.DEGRADED.value,
                ConnectionStatus.CONNECTING.value,
                ConnectionStatus.PENDING.value,
            }:
                _transition(connection, ConnectionStatus.ERROR.value)
            connection.health = ConnectionHealth.FAILED.value

    def mark_healthy(self, connection: AppConnection) -> None:
        """Clear transient errors and restore ACTIVE after a successful check/sync."""
        connection.health = ConnectionHealth.HEALTHY.value
        connection.last_error_code = None
        connection.last_error_message = None
        if connection.status == ConnectionStatus.DEGRADED.value:
            _transition(connection, ConnectionStatus.ACTIVE.value)
        elif connection.status == ConnectionStatus.ERROR.value:
            # Recoverable path (e.g. health check after transient provider blip).
            _transition(connection, ConnectionStatus.ACTIVE.value)

    def _connection_limit(self, workspace_id: uuid.UUID, app_slug: str) -> int:
        raw = self.entitlements.get(
            workspace_id, app_slug=app_slug, key=CONNECTIONS_ENTITLEMENT_KEY, default=1
        )
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 1

    def _supports_sync(self, connector_key: str) -> bool:
        caps = self.registry.capabilities(connector_key)
        return bool(caps and caps.supports_sync)

    def _ensure_routing_token(self, connection: AppConnection) -> str:
        """Return existing routing token, or mint one if missing.

        Never rotate an existing token — providers (OpenWA webhooks) bind to the URL.
        """
        if connection.webhook_routing_token_encrypted and connection.webhook_routing_token_hash:
            try:
                return decrypt_secret(
                    connection.webhook_routing_token_encrypted, settings=self.settings
                )
            except Exception:  # noqa: BLE001
                # Corrupt ciphertext — mint a replacement.
                pass
        token = generate_routing_token()
        connection.webhook_routing_token_hash = hash_routing_token(token)
        connection.webhook_routing_token_encrypted = encrypt_secret(
            token, settings=self.settings
        )
        return token

    def _require_app_and_installation(
        self,
        workspace_id: uuid.UUID,
        app_slug: str,
        *,
        require_active_access: bool,
    ) -> tuple[CatalogApp, AppInstallation | None]:
        app = self.catalog.get_app_by_slug(app_slug)
        if app is None:
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")
        installation = self.catalog.get_installation_by_app(workspace_id, app.id)
        if require_active_access:
            self.access.require_active(workspace_id, app_slug=app_slug)
            if (
                installation is None
                or installation.status != AppInstallationStatus.ACTIVE.value
            ):
                raise AppError(
                    ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
                    "App must be installed before connecting.",
                )
            if installation.workspace_id != workspace_id:
                raise AppError(
                    ErrorCategory.FORBIDDEN,
                    "Installation does not belong to this workspace.",
                )
        return app, installation
