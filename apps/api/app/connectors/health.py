"""Connector health check service (Phase 9C)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.apps_catalog.policy import can_connect_apps, can_manage_apps
from app.common.security_log import security_log
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.sanitize import sanitize_error_message
from app.connectors.schemas import AppConnectionOut, to_connection_out
from app.connectors.service import ConnectorConnectionService
from app.connectors.types import ConnectionHealth
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace

logger = logging.getLogger(__name__)


class ConnectorHealthService:
    def __init__(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or connector_registry
        self.connections = ConnectorConnectionService(db, registry=self.registry)
        self.credentials = ConnectorCredentialService(db)

    def health_check(
        self,
        *,
        workspace: Workspace,
        membership,
        actor_id: uuid.UUID,
        app_slug: str,
        connection_id: uuid.UUID,
    ) -> AppConnectionOut:
        if not can_connect_apps(membership):
            raise AppError(
                ErrorCategory.FORBIDDEN,
                "Only owners and admins can run connection health checks.",
            )
        row, app, _installation = self.connections.require_usable_connection(
            workspace.id, connection_id, app_slug=app_slug
        )
        if not self.registry.is_available(row.connector_key):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "Connector adapter is not available.",
                details={"connector_key": row.connector_key},
            )
        adapter = self.registry.get(row.connector_key)
        creds = self.credentials.get_credentials(row)
        if creds is None:
            raise AppError(
                ErrorCategory.CONNECTOR_CREDENTIALS_INVALID,
                "Connection has no credentials.",
            )

        try:
            result = adapter.health_check(
                credentials=creds,
                connection_id=row.id,
                workspace_id=workspace.id,
            )
        except Exception as exc:  # noqa: BLE001
            msg = sanitize_error_message(str(exc))
            self.connections.record_error(
                row,
                error_code=ErrorCategory.CONNECTOR_HEALTH_CHECK_FAILED.value,
                error_message=msg,
                degrade=True,
            )
            self.db.flush()
            raise AppError(
                ErrorCategory.CONNECTOR_HEALTH_CHECK_FAILED,
                "Connection health check failed.",
                details={"error_code": ErrorCategory.CONNECTOR_HEALTH_CHECK_FAILED.value},
            ) from exc

        now = datetime.now(timezone.utc)
        row.last_health_check_at = now
        row.health = (
            result.health.value
            if isinstance(result.health, ConnectionHealth)
            else str(result.health)
        )
        if result.health == ConnectionHealth.HEALTHY:
            row.last_success_at = now
            self.connections.mark_healthy(row)
        elif result.error_code or result.error_message:
            row.last_error_code = result.error_code
            row.last_error_message = sanitize_error_message(result.error_message)
            row.last_error_at = now
            if result.health in {ConnectionHealth.DEGRADED, ConnectionHealth.FAILED}:
                self.connections.record_error(
                    row,
                    error_code=result.error_code
                    or ErrorCategory.CONNECTOR_HEALTH_CHECK_FAILED.value,
                    error_message=result.error_message,
                    degrade=result.health == ConnectionHealth.DEGRADED,
                )
        self.db.flush()
        security_log(
            "app.connection.health_checked",
            workspace_id=str(workspace.id),
            actor_id=str(actor_id),
            app_id=str(app.id),
            installation_id=str(row.app_installation_id),
            connection_id=str(row.id),
            health=row.health,
        )
        return to_connection_out(
            row,
            app_slug=app.slug,
            connector_kind=app.connector_kind,
            can_manage=True,
            adapter_available=True,
            supports_sync=bool(
                self.registry.capabilities(row.connector_key)
                and self.registry.capabilities(row.connector_key).supports_sync
            ),
        )
