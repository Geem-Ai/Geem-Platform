"""Shared policy for MCP App-access loss at the model boundary."""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory


# Losing commercial/source access before an MCP dispatch is not a failure of
# the user's ordinary Expert turn. These categories select the original RAG
# path before the first model call, or a tool-free safe synthesis after a model
# tool call. Infrastructure/database failures are deliberately excluded so an
# outage is never disguised as an access decision.
MCP_ACCESS_DENIAL_CATEGORIES = frozenset(
    {
        ErrorCategory.APP_NOT_AVAILABLE,
        ErrorCategory.APP_NOT_INSTALLED,
        ErrorCategory.APP_BILLING_REQUIRED,
        ErrorCategory.APP_SUBSCRIPTION_REQUIRED,
        ErrorCategory.APP_SUBSCRIPTION_EXPIRED,
        ErrorCategory.CONNECTOR_ACCESS_REQUIRED,
        ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
    }
)


def is_mcp_access_denial(error: AppError) -> bool:
    return error.category in MCP_ACCESS_DENIAL_CATEGORIES


__all__ = ["MCP_ACCESS_DENIAL_CATEGORIES", "is_mcp_access_denial"]
