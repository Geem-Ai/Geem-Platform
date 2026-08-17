"""Provider-neutral OAuth token merge / expiry helpers (Phase 9E).

Extracted from Google Drive 9D so Microsoft OneDrive (and future providers)
share refresh-token preservation and skew logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Refresh when fewer than this many seconds remain.
REFRESH_SKEW_SECONDS = 120


def merge_token_response(
    old: dict[str, Any] | None, new: dict[str, Any]
) -> dict[str, Any]:
    """Merge OAuth token payloads — never overwrite refresh_token with null/missing."""
    merged: dict[str, Any] = dict(old or {})
    for key, value in new.items():
        if key == "refresh_token" and (value is None or value == ""):
            continue
        merged[key] = value
    if not merged.get("refresh_token") and old and old.get("refresh_token"):
        merged["refresh_token"] = old["refresh_token"]
    return merged


def parse_expires_at(credentials: dict[str, Any]) -> datetime | None:
    raw = credentials.get("expires_at")
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    expires_in = credentials.get("expires_in")
    if expires_in is not None:
        try:
            return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            return None
    return None


def credentials_need_refresh(
    credentials: dict[str, Any],
    *,
    skew_seconds: int = REFRESH_SKEW_SECONDS,
) -> bool:
    if not credentials.get("access_token"):
        return True
    expires_at = parse_expires_at(credentials)
    if expires_at is None:
        return False
    return expires_at <= datetime.now(timezone.utc) + timedelta(seconds=skew_seconds)


def apply_token_response(
    credentials: dict[str, Any], token_payload: dict[str, Any]
) -> dict[str, Any]:
    merged = merge_token_response(credentials, token_payload)
    expires_in = token_payload.get("expires_in")
    if expires_in is not None:
        try:
            merged["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            ).isoformat()
        except (TypeError, ValueError):
            pass
    scope = token_payload.get("scope")
    if scope:
        merged["granted_scopes"] = (
            scope.split() if isinstance(scope, str) else list(scope)
        )
    if token_payload.get("token_type"):
        merged["token_type"] = token_payload["token_type"]
    return merged


def expires_at_from_credentials(credentials: dict[str, Any]) -> datetime | None:
    return parse_expires_at(credentials)
