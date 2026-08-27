"""Tool-capable model boundary for Geem-owned remote MCP loops."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.agent.schemas import AgentProviderResult
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

_REQUIRED_CAPABILITIES = frozenset(
    {"function_calling", "parallel_tool_calls_false"}
)


class InvalidToolProviderOutput(AppError):
    """A metered provider response that cannot be admitted as a tool call.

    The raw, untrusted call is deliberately not retained.  ``accounting_result``
    contains only validated usage and provider identifiers so the executor can
    charge the rejected generation before performing one strict tool-free
    finalization.
    """

    def __init__(
        self,
        message: str,
        *,
        accounting_result: AgentProviderResult,
    ) -> None:
        self.accounting_result = accounting_result
        super().__init__(
            ErrorCategory.GENERATION_FAILED,
            message,
            retryable=False,
        )


class ToolCapableChatProvider(Protocol):
    def answer_with_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        system_prompt: str,
        tools: Sequence[Mapping[str, Any]],
        json_response: bool = False,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AgentProviderResult: ...

    def answer_without_tools(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str,
        system_prompt: str,
        fallback_content: str,
        json_response: bool = False,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> AgentProviderResult: ...


def select_tool_capable_model(settings: Settings) -> str:
    """Choose exactly one reviewed model before reserving a tool-loop turn."""

    raw = getattr(settings, "mcp_tool_provider_capability_matrix", "{}") or "{}"
    try:
        matrix = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
            "MCP tool-provider capability configuration is invalid.",
        ) from exc
    if not isinstance(matrix, dict):
        raise AppError(
            ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
            "MCP tool-provider capability configuration is invalid.",
        )

    for candidate in (
        settings.openrouter_chat_model,
        settings.openrouter_chat_fallback_model,
    ):
        model = (candidate or "").strip()
        declared = matrix.get(model)
        capabilities = (
            {str(value).strip() for value in declared if str(value).strip()}
            if isinstance(declared, list)
            else set()
        )
        if model and _REQUIRED_CAPABILITIES.issubset(capabilities):
            return model
    raise AppError(
        ErrorCategory.MCP_PROTOCOL_UNSUPPORTED,
        "No configured model is approved for the MCP tool loop.",
    )


__all__ = [
    "InvalidToolProviderOutput",
    "ToolCapableChatProvider",
    "select_tool_capable_model",
]
