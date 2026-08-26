"""Audience-bound Widget MCP session tokens and opaque turn handles."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass

from app.widgets.origins import normalize_origin

_SESSION_PURPOSE = b"geem-widget-mcp-session:v2"
_TURN_PURPOSE = b"geem-widget-mcp-turn:v1"
_INITIAL_SESSION_PURPOSE = b"geem-widget-mcp-initial-session:v1"
_CLIENT_TURN_ID = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_TURN_HANDLE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_MAX_SESSION_TOKEN_CHARS = 2_048


@dataclass(frozen=True, slots=True)
class WidgetMcpSession:
    session_id: str
    widget_id: uuid.UUID
    origin_digest: str
    expires_at: int


def mint_widget_mcp_session(
    *,
    session_id: str,
    widget_id: uuid.UUID,
    origin_digest: str,
    ttl_seconds: int,
    secret: str,
) -> str:
    payload = {
        "exp": int(time.time()) + max(1, int(ttl_seconds)),
        "od": _bounded_digest(origin_digest),
        "sid": str(uuid.UUID(str(session_id))),
        "wid": str(widget_id),
    }
    encoded = _b64(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = _sign(_SESSION_PURPOSE, encoded.encode("ascii"), secret)
    return f"v2.{encoded}.{signature}"


def parse_widget_mcp_session(
    token: str,
    *,
    expected_widget_id: uuid.UUID,
    expected_origin_digest: str,
    secret: str,
    now: int | None = None,
) -> WidgetMcpSession | None:
    raw_token = (token or "").strip()
    if not raw_token or len(raw_token) > _MAX_SESSION_TOKEN_CHARS:
        return None
    parts = raw_token.split(".")
    if len(parts) != 3 or parts[0] != "v2":
        return None
    encoded, supplied = parts[1], parts[2]
    try:
        encoded_bytes = encoded.encode("ascii")
        supplied_bytes = supplied.encode("ascii")
    except UnicodeEncodeError:
        return None
    expected = _sign(_SESSION_PURPOSE, encoded_bytes, secret).encode("ascii")
    if not hmac.compare_digest(supplied_bytes, expected):
        return None
    try:
        payload = json.loads(_unb64(encoded))
        session_id = str(uuid.UUID(str(payload["sid"])))
        widget_id = uuid.UUID(str(payload["wid"]))
        origin = _bounded_digest(str(payload["od"]))
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError):
        return None
    moment = int(time.time()) if now is None else int(now)
    if (
        expires_at <= moment
        or widget_id != expected_widget_id
        or not hmac.compare_digest(origin, _bounded_digest(expected_origin_digest))
    ):
        return None
    return WidgetMcpSession(session_id, widget_id, origin, expires_at)


def new_turn_handle() -> str:
    """Return a high-entropy opaque value; only its keyed digest is persisted."""

    return secrets.token_urlsafe(32)


def normalize_client_turn_id(value: str) -> str:
    """Validate the client nonce that makes a first Widget POST replay-safe."""

    clean = (value or "").strip()
    if not _CLIENT_TURN_ID.fullmatch(clean):
        raise ValueError(
            "client_turn_id must be a 32 to 128 character base64url-style nonce."
        )
    return clean


def derive_initial_widget_session_id(
    *,
    client_turn_id: str,
    widget_id: uuid.UUID,
    origin_digest: str,
    secret: str,
) -> str:
    """Derive the hidden first-session identity before a token can be received.

    A first request may disconnect before its accepted event. Deriving this UUID
    from the high-entropy client nonce and exact Widget audience lets a retry
    reacquire the same generation lock, conversation binding, and receipt while
    still persisting neither the raw nonce nor a bearer credential.
    """

    clean = normalize_client_turn_id(client_turn_id)
    context = "\x1f".join(
        (str(widget_id), _bounded_digest(origin_digest), clean)
    ).encode("utf-8")
    key = hashlib.sha256(
        _INITIAL_SESSION_PURPOSE + secret.encode("utf-8")
    ).digest()
    raw = bytearray(hmac.new(key, context, hashlib.sha256).digest()[:16])
    # Encode an RFC 4122 variant/version UUID without weakening the HMAC input.
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def derive_turn_handle(
    *,
    client_turn_id: str,
    widget_id: uuid.UUID,
    session_id: str,
    origin_digest: str,
    secret: str,
) -> str:
    """Deterministic opaque handle so a safe client retry gets the same turn."""

    clean = normalize_client_turn_id(client_turn_id)
    context = "\x1f".join(
        (
            str(widget_id),
            str(uuid.UUID(str(session_id))),
            _bounded_digest(origin_digest),
            clean,
        )
    ).encode("utf-8")
    digest = hmac.new(
        hashlib.sha256(_TURN_PURPOSE + secret.encode("utf-8")).digest(),
        b"derive\x00" + context,
        hashlib.sha256,
    ).digest()
    return _b64(digest)


def turn_handle_digest(
    raw_handle: str,
    *,
    widget_id: uuid.UUID,
    session_id: str,
    origin_digest: str,
    secret: str,
) -> str:
    handle = (raw_handle or "").strip()
    if not _TURN_HANDLE.fullmatch(handle):
        raise ValueError("A high-entropy opaque Widget turn handle is required.")
    context = "\x1f".join(
        (
            str(widget_id),
            str(uuid.UUID(str(session_id))),
            _bounded_digest(origin_digest),
            handle,
        )
    ).encode("utf-8")
    return hmac.new(
        hashlib.sha256(_TURN_PURPOSE + secret.encode("utf-8")).digest(),
        context,
        hashlib.sha256,
    ).hexdigest()


def origin_digest(origin: str, *, secret: str) -> str:
    normalized = normalize_origin(origin)
    return hmac.new(
        hashlib.sha256(secret.encode("utf-8")).digest(),
        b"geem-widget-origin:v1\x00" + normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def external_principal_digest(
    principal: str,
    *,
    audience: str,
    secret: str,
) -> str:
    """Purpose-separated keyed digest for a Widget session or channel sender."""

    clean_principal = (principal or "").strip()
    clean_audience = (audience or "").strip()
    if not clean_principal or not clean_audience:
        raise ValueError("An external principal and audience are required.")
    key = hashlib.sha256(
        b"geem-mcp-external-principal:v1\x00" + secret.encode("utf-8")
    ).digest()
    return hmac.new(
        key,
        f"{clean_audience}\x1f{clean_principal}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def widget_external_principal_fingerprint(
    session_id: str,
    *,
    widget_id: uuid.UUID,
    secret: str,
) -> str:
    """Derive the exact Widget visitor identity used by runtime admission."""

    return external_principal_digest(
        str(uuid.UUID(str(session_id))),
        audience=f"widget:{widget_id}",
        secret=secret,
    )


def channel_external_principal_fingerprint(
    *,
    external_chat_id: str,
    external_sender_id: str | None,
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    binding_id: uuid.UUID,
    secret: str,
) -> str:
    """Derive the exact WhatsApp direct-chat/sender runtime identity."""

    chat_id = (external_chat_id or "").strip()
    sender_id = (external_sender_id or chat_id).strip()
    if not chat_id or not sender_id:
        raise ValueError("A WhatsApp chat and sender identity are required.")
    return external_principal_digest(
        f"{chat_id}\x1f{sender_id}",
        audience=f"whatsapp:{workspace_id}:{connection_id}:{binding_id}",
        secret=secret,
    )


def _sign(purpose: bytes, payload: bytes, secret: str) -> str:
    key = hashlib.sha256(purpose + secret.encode("utf-8")).digest()
    return _b64(hmac.new(key, payload, hashlib.sha256).digest())


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )


def _bounded_digest(value: str) -> str:
    raw = (value or "").strip().lower()
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise ValueError("A SHA-256 digest is required.")
    return raw


__all__ = [
    "WidgetMcpSession",
    "derive_initial_widget_session_id",
    "derive_turn_handle",
    "channel_external_principal_fingerprint",
    "external_principal_digest",
    "mint_widget_mcp_session",
    "new_turn_handle",
    "normalize_client_turn_id",
    "origin_digest",
    "parse_widget_mcp_session",
    "turn_handle_digest",
    "widget_external_principal_fingerprint",
]
