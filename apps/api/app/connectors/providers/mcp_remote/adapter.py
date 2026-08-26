"""Registry identity for the generic remote MCP tool-source connector."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.connectors.adapters import ConnectorCapabilities, HealthCheckResult
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.types import ConnectorAuthMode, ConnectorKind, ConnectionHealth
from app.core.config import Settings, get_settings
from app.mcp.constants import MCP_CONNECTOR_KEY


@dataclass
class McpRemoteConnector:
    key: str = MCP_CONNECTOR_KEY
    kind: ConnectorKind = ConnectorKind.TOOL_SOURCE
    auth_mode: ConnectorAuthMode = ConnectorAuthMode.NONE
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            supports_oauth=True,
            supports_credentials=True,
            # MCP inventory polling is owned by the dedicated discovery API;
            # it is not generic connector knowledge synchronization.
            supports_sync=False,
            supports_webhooks=False,
            supports_health_check=True,
        )
    )
    settings: Settings | None = None

    def _settings(self) -> Settings:
        return self.settings or get_settings()

    def is_configured(self) -> bool:
        return bool(self._settings().mcp_connector_enabled)

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.is_configured() else "mcp_connector_not_enabled"

    def health_check(
        self,
        *,
        credentials: dict[str, Any],
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> HealthCheckResult:
        _ = connection_id, workspace_id
        config = credentials.get("mcp") if isinstance(credentials, dict) else None
        configured = isinstance(config, dict) and bool(config.get("server_url"))
        return HealthCheckResult(
            health=(ConnectionHealth.UNKNOWN if configured else ConnectionHealth.FAILED),
            error_code=None if configured else "connector_credentials_invalid",
            error_message=None if configured else "MCP connection configuration is missing.",
        )

    def disconnect(
        self,
        *,
        credentials: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
        sync_state: dict[str, Any] | None = None,
    ) -> None:
        # Remote MCP sessions are request-scoped. Credential cleanup is owned
        # by ConnectorCredentialService and needs no provider-side mutation.
        _ = credentials, connection_id, workspace_id, sync_state


def register_mcp_remote_connector(
    *,
    registry: ConnectorRegistry | None = None,
    settings: Settings | None = None,
) -> McpRemoteConnector:
    target = registry or connector_registry
    existing = target.try_get(MCP_CONNECTOR_KEY)
    if isinstance(existing, McpRemoteConnector):
        return existing
    adapter = McpRemoteConnector(settings=settings)
    target.register(adapter)
    return adapter


__all__ = ["McpRemoteConnector", "register_mcp_remote_connector"]
