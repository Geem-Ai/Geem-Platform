"""Safe OpenTelemetry attributes. IDs are attributes; never span names."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from opentelemetry.trace import Span, Status, StatusCode

from app.common.request_context import get_request_context
from app.connectors.sanitize import sanitize_error_message

# Cardinality rule: span names are stable operations (chat.turn, rag.retrieve).
# Never name a span after a conversation UUID, user prompt, or raw URL.

FORBIDDEN_ATTR_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "token",
        "refresh_token",
        "access_token",
        "jwt",
        "api_key",
        "api_key_value",
        "invitation_token",
        "prompt",
        "question",
        "answer",
        "content",
        "message",
        "messages",
        "system_instructions",
        "credentials",
        "secret",
        "webhook_secret",
        "smtp_password",
        "raw_prompt",
        "raw_response",
    }
)

_MAX_STRING = 256
_URL_RE = re.compile(r"https?://[^\s\"'>]+", re.IGNORECASE)


def _is_forbidden_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_").replace(".", "_")
    if normalized in FORBIDDEN_ATTR_KEYS:
        return True
    last = normalized.rsplit("_", 1)[-1]
    return last in {
        "password",
        "token",
        "jwt",
        "authorization",
        "cookie",
        "prompt",
        "question",
        "answer",
        "secret",
    }


def coerce_attr_value(value: Any) -> bool | int | float | str | None:
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, UUID):
        return str(value)
    text = str(value)
    if len(text) > _MAX_STRING:
        text = text[: _MAX_STRING - 1] + "…"
    return text


def set_safe_attributes(span: Span, attrs: dict[str, Any] | None) -> None:
    if not attrs or not span.is_recording():
        return
    for key, raw in attrs.items():
        if not key or _is_forbidden_key(key):
            continue
        value = coerce_attr_value(raw)
        if value is None:
            continue
        span.set_attribute(key, value)


def attach_request_context(span: Span | None = None) -> None:
    """Copy authorized RequestContext onto the current (or given) span."""
    if span is None:
        from opentelemetry.trace import get_current_span

        span = get_current_span()
    if not span.is_recording():
        return
    ctx = get_request_context()
    attrs: dict[str, Any] = {}
    if ctx.request_id:
        attrs["request.id"] = ctx.request_id
    if ctx.workspace_id is not None:
        attrs["workspace.id"] = str(ctx.workspace_id)
    if ctx.user_id is not None:
        attrs["user.id"] = str(ctx.user_id)
        attrs["geem.auth.type"] = "session"
    elif ctx.api_key_id is not None:
        attrs["api_key.id"] = str(ctx.api_key_id)
        attrs["geem.auth.type"] = "api_key"
    else:
        attrs["geem.auth.type"] = "anonymous"
    if ctx.workspace_resolution:
        attrs["geem.workspace.resolution"] = ctx.workspace_resolution
    set_safe_attributes(span, attrs)


def mark_span_error(span: Span, exc: BaseException) -> None:
    """Mark the span failed without recording raw exception strings (URLs, headers)."""
    if not span.is_recording():
        return
    raw = _URL_RE.sub("[url]", str(exc))
    safe = sanitize_error_message(raw, max_len=200) or type(exc).__name__
    span.set_status(Status(StatusCode.ERROR, safe))
    span.add_event(
        "exception",
        {
            "exception.type": type(exc).__name__,
            "exception.message": safe,
        },
    )
