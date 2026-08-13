"""Centralized token accounting for AI usage (Phase 5B).

Provider metadata is authoritative when present. Fallback does **not** run a
tokenizer in Chat/RAG code — callers pass a single fallback (typically the
reservation amount) after a successful generation with no usage payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TokenSource = Literal["provider", "fallback"]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int
    source: TokenSource

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "source": self.source,
        }


def _nonneg_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def parse_provider_usage(usage: Any) -> TokenUsage | None:
    """Extract prompt/completion/total from OpenRouter/OpenAI-style usage."""
    if not isinstance(usage, dict):
        return None
    prompt = _nonneg_int(usage.get("prompt_tokens") if usage.get("prompt_tokens") is not None else usage.get("input_tokens"))
    completion = _nonneg_int(
        usage.get("completion_tokens")
        if usage.get("completion_tokens") is not None
        else usage.get("output_tokens")
    )
    total = _nonneg_int(usage.get("total_tokens"))
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    elif total is None and prompt is not None:
        total = prompt
    elif total is None and completion is not None:
        total = completion
    if total is None:
        return None
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        source="provider",
    )


def chargeable_tokens(
    *,
    provider_usage: Any = None,
    fallback_tokens: int = 0,
) -> TokenUsage:
    """Prefer provider totals; otherwise charge ``fallback_tokens`` (never a tokenizer)."""
    parsed = parse_provider_usage(provider_usage)
    if parsed is not None:
        return parsed
    return TokenUsage(
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=max(0, int(fallback_tokens)),
        source="fallback",
    )


def _add_optional(left: Any, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


def merge_token_usage(existing: dict[str, Any] | None, incoming: TokenUsage) -> dict[str, Any]:
    """Sum two usage payloads (citation retry, general fallback, …)."""
    if not existing:
        return incoming.as_dict()
    source: TokenSource = (
        "provider"
        if existing.get("source") == "provider" and incoming.source == "provider"
        else incoming.source
    )
    return {
        "prompt_tokens": _add_optional(existing.get("prompt_tokens"), incoming.prompt_tokens),
        "completion_tokens": _add_optional(
            existing.get("completion_tokens"), incoming.completion_tokens
        ),
        "total_tokens": int(existing.get("total_tokens") or 0) + incoming.total_tokens,
        "source": source,
    }


def accumulate_result_usage(target: dict[str, Any], result: dict[str, Any] | None) -> None:
    """Add this LLM call's provider usage onto ``target['usage']`` when present."""
    if not result:
        return
    parsed = parse_provider_usage((result.get("_meta") or {}).get("usage"))
    if parsed is None:
        return
    target["usage"] = merge_token_usage(target.get("usage"), parsed)
