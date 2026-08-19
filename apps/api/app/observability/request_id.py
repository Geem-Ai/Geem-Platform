"""Bound incoming X-Request-Id values so callers cannot inflate logs."""

from __future__ import annotations

import re
import uuid

MAX_REQUEST_ID_LENGTH = 128
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def sanitize_request_id(raw: str | None) -> str:
    """Return a safe request id. Oversized or odd values are replaced."""
    value = (raw or "").strip()
    if not value or len(value) > MAX_REQUEST_ID_LENGTH:
        return str(uuid.uuid4())
    if not _REQUEST_ID_RE.fullmatch(value):
        return str(uuid.uuid4())
    return value
