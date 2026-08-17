"""OpenWA webhook signature verification + event normalization."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.connectors.adapters import WebhookHandleResult
from app.connectors.sanitize import sanitize_error_message

logger = logging.getLogger(__name__)

HEADER_SIGNATURE = "x-openwa-signature"
HEADER_IDEMPOTENCY = "x-openwa-idempotency-key"
HEADER_EVENT = "x-openwa-event"
HEADER_DELIVERY = "x-openwa-delivery-id"

SESSION_EVENTS = frozenset(
    {
        "session.status",
        "session.authenticated",
        "session.disconnected",
        "session.restriction",
    }
)
MESSAGE_EVENTS = frozenset({"message.received"})


@dataclass(frozen=True, slots=True)
class NormalizedChannelMessage:
    provider_message_id: str
    external_chat_id: str
    sender_id: str
    body: str
    message_type: str
    provider_timestamp: int | None
    is_group: bool
    from_me: bool
    has_media: bool
    chat_kind: str | None


def verify_openwa_signature(
    *,
    raw_body: bytes,
    signature: str | None,
    secret: str,
) -> bool:
    """HMAC-SHA256 over raw body; constant-time compare. Format: sha256=<hex>."""
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    try:
        return hmac.compare_digest(signature.strip(), expected)
    except (TypeError, ValueError):
        return False


def header_value(headers: dict[str, str], name: str) -> str | None:
    lower = {str(k).lower(): v for k, v in headers.items()}
    val = lower.get(name.lower())
    if val is None or not str(val).strip():
        return None
    return str(val).strip()


def parse_openwa_event(raw_body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid_payload")
    return data


def extract_idempotency_key(
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> str | None:
    header_key = header_value(headers, HEADER_IDEMPOTENCY)
    if header_key:
        return header_key[:512]
    body_key = payload.get("idempotencyKey") or payload.get("idempotency_key")
    if isinstance(body_key, str) and body_key.strip():
        return body_key.strip()[:512]
    return None


def extract_event_name(
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> str:
    header_event = header_value(headers, HEADER_EVENT)
    if header_event:
        return header_event
    event = payload.get("event")
    if isinstance(event, str) and event.strip():
        return event.strip()
    return ""


def normalize_message_received(payload: dict[str, Any]) -> NormalizedChannelMessage | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    msg_id = str(data.get("id") or data.get("messageId") or "").strip()
    from_raw = str(data.get("from") or "").strip()
    body = data.get("body")
    body_text = body.strip() if isinstance(body, str) else ""
    msg_type = str(data.get("type") or "chat").strip() or "chat"
    is_group = bool(data.get("isGroup"))
    from_me = bool(data.get("fromMe"))
    has_media = bool(data.get("hasMedia"))
    kind = data.get("kind")
    chat_kind = str(kind).strip() if isinstance(kind, str) else None
    ts_raw = data.get("timestamp")
    ts: int | None
    try:
        ts = int(ts_raw) if ts_raw is not None else None
    except (TypeError, ValueError):
        ts = None
    if not from_raw:
        return None
    # Prefer explicit chat id when present; else use from.
    chat_id = str(data.get("chatId") or data.get("to") or from_raw).strip() or from_raw
    if is_group and data.get("from"):
        # For groups, `from` is often the participant; chat id may be in chatId / remote.
        chat_id = str(
            data.get("chatId") or data.get("remote") or data.get("to") or from_raw
        ).strip()
    return NormalizedChannelMessage(
        provider_message_id=msg_id
        or _synthetic_provider_message_id(from_raw, ts, body_text),
        external_chat_id=chat_id,
        sender_id=from_raw,
        body=body_text,
        message_type=msg_type,
        provider_timestamp=ts,
        is_group=is_group,
        from_me=from_me,
        has_media=has_media,
        chat_kind=chat_kind,
    )


def _synthetic_provider_message_id(
    from_raw: str, ts: int | None, body_text: str
) -> str:
    """Stable across workers — never use process-local ``hash()``."""
    digest = hashlib.sha256(
        f"{from_raw}|{ts or 0}|{body_text}".encode("utf-8")
    ).hexdigest()[:32]
    return f"{from_raw}:{ts or 0}:{digest}"


def extract_session_status(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (status, last_error) from session.* webhook payloads."""
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    status = data.get("status") if isinstance(data, dict) else None
    if not isinstance(status, str) or not status.strip():
        status = payload.get("status")
    last_error = None
    if isinstance(data, dict):
        err = data.get("lastError") or data.get("last_error") or data.get("error")
        if isinstance(err, str) and err.strip():
            last_error = sanitize_error_message(err.strip())
        elif isinstance(err, dict):
            msg = err.get("message") or err.get("code")
            if isinstance(msg, str) and msg.strip():
                last_error = sanitize_error_message(msg.strip())
    status_s = status.strip() if isinstance(status, str) else None
    return status_s, last_error


def build_webhook_handle_result(
    *,
    accepted: bool,
    idempotency_key: str | None,
    enqueue: bool,
    enqueue_payload: dict[str, Any] | None = None,
    ignore: bool = False,
    error_code: str | None = None,
    provider_event_id: str | None = None,
) -> WebhookHandleResult:
    return WebhookHandleResult(
        accepted=accepted,
        provider_event_id=provider_event_id,
        idempotency_key=idempotency_key,
        enqueue=enqueue,
        enqueue_payload=dict(enqueue_payload or {}),
        http_status=200 if accepted else 401,
        ignore=ignore,
        error_code=error_code,
    )
