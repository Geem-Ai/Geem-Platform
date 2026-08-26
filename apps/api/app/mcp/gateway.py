"""Application-side contract for the isolated MCP egress gateway.

The gateway implementation is intentionally not in this package.  Ordinary API
and worker processes resolve tenancy and decrypt exactly one connection, then
pass one bounded operation envelope to the mTLS-only gateway.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol, runtime_checkable

from app.core.errors import AppError, ErrorCategory


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class McpDiscoveryRequest:
    workspace_id: uuid.UUID
    connection_id: uuid.UUID
    server_url: str
    resource_uri: str
    auth: dict[str, Any]
    credential_epoch: int
    deadline_seconds: float


@dataclass(frozen=True, slots=True)
class McpDiscoveryResult:
    protocol_version: str
    session_mode: str
    capabilities: dict[str, Any]
    tools: tuple[dict[str, Any], ...]
    complete: bool = True
    external_subject: str | None = None
    external_identity_label: str | None = None
    issuer: str | None = None
    client_id: str | None = None
    resource_uri: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class McpTargetValidationRequest:
    workspace_id: uuid.UUID
    connection_id: uuid.UUID
    target_url: str
    deadline_seconds: float
    operation_name: str = "validate"


@dataclass(frozen=True, slots=True)
class McpTargetValidationResult:
    origin_digest: str


@runtime_checkable
class McpGatewayClient(Protocol):
    def validate_target(
        self,
        request: McpTargetValidationRequest,
    ) -> McpTargetValidationResult: ...

    def discover(self, request: McpDiscoveryRequest) -> McpDiscoveryResult: ...

    def call_tool(self, request: Any) -> Any: ...


class UnavailableMcpGatewayClient:
    """Fail-closed default until an authenticated gateway client is injected."""

    def validate_target(
        self,
        request: McpTargetValidationRequest,
    ) -> McpTargetValidationResult:
        del request
        raise AppError(
            ErrorCategory.MCP_SERVER_UNREACHABLE,
            "The MCP egress gateway is unavailable.",
            retryable=True,
        )

    def discover(self, request: McpDiscoveryRequest) -> McpDiscoveryResult:
        del request
        raise AppError(
            ErrorCategory.MCP_SERVER_UNREACHABLE,
            "The MCP egress gateway is unavailable.",
            retryable=True,
        )

    def call_tool(self, request: Any) -> Any:
        del request
        raise AppError(
            ErrorCategory.MCP_SERVER_UNREACHABLE,
            "The MCP egress gateway is unavailable.",
            retryable=True,
        )


_gateway_client: McpGatewayClient = UnavailableMcpGatewayClient()
_gateway_client_pid = os.getpid()
_gateway_client_initialization_failed = False
_gateway_client_lock = Lock()


def get_mcp_gateway_client() -> McpGatewayClient:
    """Return the configured process-local gateway adapter.

    Application startup may replace the fail-closed default with the mTLS
    client.  Keeping the interface here makes discovery easy to exercise with
    an in-memory fake without importing transport code into the domain layer.
    """

    global _gateway_client, _gateway_client_initialization_failed, _gateway_client_pid
    current_pid = os.getpid()
    if (
        _gateway_client_pid == current_pid
        and (
            _gateway_client_initialization_failed
            or not isinstance(_gateway_client, UnavailableMcpGatewayClient)
        )
    ):
        return _gateway_client

    from app.core.config import get_settings

    settings = get_settings()
    with _gateway_client_lock:
        # A pre-fork HTTP pool must never be reused by a child API/worker
        # process. Discard the inherited reference and initialize locally.
        if _gateway_client_pid != current_pid:
            _gateway_client = UnavailableMcpGatewayClient()
            _gateway_client_initialization_failed = False
            _gateway_client_pid = current_pid
        if _gateway_client_initialization_failed:
            return _gateway_client
        if not isinstance(_gateway_client, UnavailableMcpGatewayClient):
            return _gateway_client
        if not settings.mcp_connector_enabled:
            return _gateway_client
        try:
            # Local import preserves the protocol module/client dependency
            # direction while giving both API and Celery processes the same
            # fail-closed lazy runtime factory.
            from app.mcp.gateway_client import HttpMcpGatewayClient

            _gateway_client = HttpMcpGatewayClient(settings)
        except Exception:
            # TLS paths and internal gateway configuration are sensitive. Do
            # not serialize or log the initialization exception; operations
            # retain the fixed unavailable-client behavior.
            logger.error("mcp_gateway_client_initialization_failed")
            _gateway_client = UnavailableMcpGatewayClient()
            _gateway_client_initialization_failed = True
        _gateway_client_pid = current_pid
    return _gateway_client


def set_mcp_gateway_client(client: McpGatewayClient) -> None:
    """Install the authenticated gateway adapter during application startup."""

    global _gateway_client, _gateway_client_initialization_failed, _gateway_client_pid
    with _gateway_client_lock:
        _gateway_client = client
        _gateway_client_initialization_failed = False
        _gateway_client_pid = os.getpid()


def reset_mcp_gateway_client() -> None:
    """Restore the deterministic fail-closed default (primarily for tests)."""

    global _gateway_client, _gateway_client_initialization_failed, _gateway_client_pid
    with _gateway_client_lock:
        _gateway_client = UnavailableMcpGatewayClient()
        _gateway_client_initialization_failed = False
        _gateway_client_pid = os.getpid()


__all__ = [
    "McpDiscoveryRequest",
    "McpDiscoveryResult",
    "McpGatewayClient",
    "McpTargetValidationRequest",
    "McpTargetValidationResult",
    "UnavailableMcpGatewayClient",
    "get_mcp_gateway_client",
    "reset_mcp_gateway_client",
    "set_mcp_gateway_client",
]
