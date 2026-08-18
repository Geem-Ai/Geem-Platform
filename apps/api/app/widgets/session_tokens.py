"""HMAC-signed Chat Widget visitor session tokens."""

from __future__ import annotations

import hashlib
import hmac
import uuid

from app.core.errors import AppError, ErrorCategory

_PURPOSE = "geem-widget-session:v1"
_SIG_LEN = 32  # hex chars truncated from SHA-256


def _mac(secret: str, session_uuid: str) -> str:
    digest = hmac.new(
        (secret or "").encode("utf-8"),
        f"{_PURPOSE}:{session_uuid}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:_SIG_LEN]


def mint_session_token(session_uuid: str, *, secret: str) -> str:
    sid = str(uuid.UUID(str(session_uuid)))
    return f"{sid}.{_mac(secret, sid)}"


def parse_session_token(token: str, *, secret: str) -> str | None:
    """Return the session UUID if the HMAC is valid; otherwise None."""
    raw = (token or "").strip()
    if not raw or "." not in raw:
        return None
    sid, sig = raw.rsplit(".", 1)
    if len(sig) != _SIG_LEN:
        return None
    try:
        sid = str(uuid.UUID(sid))
    except ValueError:
        return None
    expected = _mac(secret, sid)
    if not hmac.compare_digest(sig, expected):
        return None
    return sid


def parse_bare_session_uuid(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw or "." in raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


def require_session_uuid(token: str | None, *, secret: str) -> tuple[str, str]:
    """Mint or verify a session token.

    Returns ``(session_uuid, token_for_client)``.
    Bare UUIDs are not accepted here — callers may grandfather existing bindings.
    """
    raw = (token or "").strip()
    if not raw:
        sid = str(uuid.uuid4())
        return sid, mint_session_token(sid, secret=secret)

    parsed = parse_session_token(raw, secret=secret)
    if parsed is not None:
        return parsed, mint_session_token(parsed, secret=secret)

    raise AppError(
        ErrorCategory.VALIDATION,
        "Invalid session_id.",
    )
