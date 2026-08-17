"""Sanitize provider errors before persistence / public DTOs."""

from __future__ import annotations

import re
from typing import Any

# Never persist or return these to end users.
_DEFAULT_PUBLIC_MESSAGE = "Something went wrong. Please try again."

# Patterns that may appear in exception strings / provider bodies.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(access[_-]?token|refresh[_-]?token|api[_-]?key|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)authorization:\s*\S+"),
    re.compile(r"(?i)code_verifier[=:]\s*\S+"),
    re.compile(r"ya29\.[A-Za-z0-9_-]+"),  # Google-style access tokens
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT-ish
)

_TECHNICAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(psycopg|sqlalchemy|asyncpg|celery|traceback|CheckViolation|"
        r"IntegrityError|OperationalError|ProgrammingError|DataError)\b"
    ),
    re.compile(r"(?i)violates check constraint"),
    re.compile(r"(?i)\bSQL:\s*(INSERT|UPDATE|SELECT|DELETE|WITH)\b"),
    re.compile(r'(?i)File "[^"]+\.py"'),
    re.compile(r"(?i)site-packages"),
    re.compile(r"(?i)DETAIL:\s*Failing row"),
    re.compile(r"(?i)background on this error at:"),
    re.compile(r"(?i)\[SQL:\s*"),
)


def looks_technical(raw: str | None) -> bool:
    """True when a string looks like a stack dump / DB / ORM error."""
    if raw is None:
        return False
    text = str(raw).strip()
    if not text:
        return False
    if len(text) > 280:
        return True
    return any(pattern.search(text) for pattern in _TECHNICAL_PATTERNS)


def sanitize_error_message(raw: str | None, *, max_len: int = 500) -> str | None:
    """Redact secrets and replace technical internals with a safe public message."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    # Strip query-ish secrets from URLs
    text = re.sub(
        r"([?&](?:access_token|refresh_token|code|client_secret|api_key)=)[^&\s]+",
        r"\1[redacted]",
        text,
        flags=re.IGNORECASE,
    )
    if looks_technical(text):
        return _DEFAULT_PUBLIC_MESSAGE
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def sanitize_log_fields(**fields: Any) -> dict[str, Any]:
    blocked = {
        "access_token",
        "refresh_token",
        "api_key",
        "client_secret",
        "code_verifier",
        "authorization_code",
        "code",
        "credentials",
        "webhook_secret",
        "delta_link",
        "sync_cursor",
        "pkce",
        "raw_body",
        "payload",
    }
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower().replace("-", "_") in blocked:
            continue
        if isinstance(value, str):
            safe[key] = sanitize_error_message(value, max_len=200) or value
        else:
            safe[key] = value
    return safe
