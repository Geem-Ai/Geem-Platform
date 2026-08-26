"""Stable MCP product and normalization identifiers."""

from __future__ import annotations

from app.apps_catalog.mcp_product import (
    MCP_CONNECTIONS_ENTITLEMENT,
    MCP_CONNECTOR_KEY,
    MCP_CONNECTORS_APP_SLUG,
)

MCP_NORMALIZATION_VERSION = "mcp-tool-definition-v1"
MCP_TOOL_ALIAS_MAX_LENGTH = 64
MCP_TOOL_NAME_MAX_LENGTH = 256
MCP_TOOL_DESCRIPTOR_MAX_BYTES = 262_144

# Generic MCP static authentication deliberately accepts a very small contract.
# Additional proprietary headers require a reviewed connector adapter.
MCP_STATIC_HEADER_ALLOWLIST = frozenset(
    {
        "authorization",
        "x-api-key",
        "x-auth-token",
    }
)

MCP_FORBIDDEN_AUTH_HEADERS = frozenset(
    {
        "cookie",
        "set-cookie",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
        "mcp-protocol-version",
        "mcp-session-id",
        "mcp-method",
        "mcp-name",
    }
)

# Model-generated schema parameters may be projected into ordinary request
# headers only when they cannot collide with credentials, routing, transport,
# proxy, or MCP protocol state.
MCP_ARGUMENT_HEADER_FORBIDDEN = MCP_FORBIDDEN_AUTH_HEADERS | frozenset(
    {
        "accept",
        "accept-encoding",
        "authorization",
        "content-type",
        "cookie",
        "forwarded",
        "last-event-id",
        "origin",
        "referer",
        "user-agent",
        "x-api-key",
        "x-auth-token",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
    }
)

__all__ = [
    "MCP_CONNECTIONS_ENTITLEMENT",
    "MCP_ARGUMENT_HEADER_FORBIDDEN",
    "MCP_CONNECTOR_KEY",
    "MCP_CONNECTORS_APP_SLUG",
    "MCP_FORBIDDEN_AUTH_HEADERS",
    "MCP_NORMALIZATION_VERSION",
    "MCP_STATIC_HEADER_ALLOWLIST",
    "MCP_TOOL_ALIAS_MAX_LENGTH",
    "MCP_TOOL_DESCRIPTOR_MAX_BYTES",
    "MCP_TOOL_NAME_MAX_LENGTH",
]
