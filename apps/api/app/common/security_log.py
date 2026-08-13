from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("geem.security")

_BLOCKED_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "refresh_token",
        "refreshtoken",
        "access_token",
        "accesstoken",
        "authorization",
        "secret",
        "cookie",
        "raw_refresh_token",
        "system_instructions",
        "credentials",
        "server_key",
        "client_key",
        "profile_id",
        "secrets_encryption_key",
    }
)


def security_log(event: str, **fields: Any) -> None:
    """Structured security/audit-oriented log. Never pass passwords or raw tokens."""
    safe = {k: v for k, v in fields.items() if k.lower().replace("-", "_") not in _BLOCKED_KEYS}
    logger.info(event, extra={"security_event": event, **safe})
