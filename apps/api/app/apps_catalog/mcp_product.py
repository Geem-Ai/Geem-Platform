"""Locked identifiers for the paid MCP Connectors product (Phase 13)."""

from __future__ import annotations

MCP_CONNECTORS_APP_SLUG = "mcp-connectors"
MCP_CONNECTOR_KEY = "mcp_remote"
MCP_CONNECTOR_KIND = "tool_source"

MCP_CONNECTIONS_ENTITLEMENT = "connections"
MCP_TOOL_CALLS_DAILY_ENTITLEMENT = "tool_calls_daily"
MCP_TOOL_CALLS_USAGE_METRIC = "app:mcp-connectors:tool_calls"

MCP_PLAN_CODES: tuple[str, ...] = (
    "mcp-starter",
    "mcp-team",
    "mcp-scale",
)
MCP_PLAN_CONNECTION_LIMITS: tuple[int, ...] = (1, 3, 10)
MCP_PLAN_TOOL_CALL_LIMITS: tuple[int, ...] = (200, 1_000, 5_000)

__all__ = [
    "MCP_CONNECTIONS_ENTITLEMENT",
    "MCP_CONNECTOR_KEY",
    "MCP_CONNECTOR_KIND",
    "MCP_CONNECTORS_APP_SLUG",
    "MCP_PLAN_CODES",
    "MCP_PLAN_CONNECTION_LIMITS",
    "MCP_PLAN_TOOL_CALL_LIMITS",
    "MCP_TOOL_CALLS_DAILY_ENTITLEMENT",
    "MCP_TOOL_CALLS_USAGE_METRIC",
]
