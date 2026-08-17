"""Google Drive changes.watch helpers (Phase 9D).

Watch channels expire (~1 day max from Google). Celery beat renews them
via ``renew_google_drive_watches`` about every 6 hours when expiration is
within 24 hours.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.connectors.providers.google_drive.client import GoogleDriveClient
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

WATCH_RENEW_WITHIN = timedelta(hours=24)


def watch_fields_from_sync_state(sync_state: dict[str, Any] | None) -> dict[str, Any]:
    state = sync_state or {}
    return {
        "channel_id": state.get("watch_channel_id"),
        "resource_id": state.get("watch_resource_id"),
        "channel_token": state.get("watch_channel_token"),
        "expiration": state.get("watch_expiration"),
    }


def watch_needs_renewal(sync_state: dict[str, Any] | None) -> bool:
    fields = watch_fields_from_sync_state(sync_state)
    if not fields.get("channel_id") or not fields.get("resource_id"):
        return True
    raw = fields.get("expiration")
    if raw is None:
        return True
    try:
        if isinstance(raw, (int, float)):
            # Google returns expiration as epoch milliseconds.
            exp = datetime.fromtimestamp(float(raw) / 1000.0, tz=timezone.utc)
        else:
            exp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OSError):
        return True
    return exp <= datetime.now(timezone.utc) + WATCH_RENEW_WITHIN


def webhook_address(
    *,
    settings: Settings | None = None,
    routing_token: str,
) -> str:
    settings = settings or get_settings()
    base = (settings.app_url or "").rstrip("/")
    return f"{base}/api/connectors/webhooks/google_drive/{routing_token}"


def ensure_changes_watch(
    client: GoogleDriveClient,
    *,
    sync_state: dict[str, Any],
    page_token: str,
    routing_token: str,
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create or renew changes.watch; return updated sync_state fragment."""
    settings = settings or get_settings()
    state = dict(sync_state or {})
    if not force and not watch_needs_renewal(state):
        return state

    # Stop previous channel best-effort before creating a new one.
    old_id = state.get("watch_channel_id")
    old_resource = state.get("watch_resource_id")
    if old_id and old_resource:
        client.stop_channel(channel_id=str(old_id), resource_id=str(old_resource))

    channel_id = str(uuid.uuid4())
    channel_token = secrets.token_urlsafe(24)
    address = webhook_address(settings=settings, routing_token=routing_token)
    try:
        # Ask for ~7 days; Google may clamp to ~1 day.
        expiration_ms = int(
            (datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000
        )
        result = client.create_changes_watch(
            page_token=page_token,
            channel_id=channel_id,
            address=address,
            channel_token=channel_token,
            expiration_ms=expiration_ms,
        )
    except AppError as exc:
        if exc.category == ErrorCategory.GOOGLE_DRIVE_RATE_LIMITED:
            raise
        raise AppError(
            ErrorCategory.GOOGLE_DRIVE_WATCH_FAILED,
            exc.message or "Failed to create Google Drive watch channel.",
        ) from exc

    state["watch_channel_id"] = result.get("id") or channel_id
    state["watch_resource_id"] = result.get("resourceId")
    state["watch_channel_token"] = channel_token
    exp = result.get("expiration")
    if exp is not None:
        state["watch_expiration"] = exp
    return state


def validate_webhook_headers(
    *,
    headers: dict[str, str],
    sync_state: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Return (ok, resource_state). Reject channel mismatches."""
    state = sync_state or {}
    channel_id = headers.get("x-goog-channel-id") or headers.get("X-Goog-Channel-ID")
    channel_token = headers.get("x-goog-channel-token") or headers.get(
        "X-Goog-Channel-Token"
    )
    resource_id = headers.get("x-goog-resource-id") or headers.get("X-Goog-Resource-ID")
    resource_state = (
        headers.get("x-goog-resource-state")
        or headers.get("X-Goog-Resource-State")
        or ""
    ).lower()

    expected_id = state.get("watch_channel_id")
    expected_token = state.get("watch_channel_token")
    expected_resource = state.get("watch_resource_id")

    if not expected_id or not expected_token or not expected_resource:
        return False, None
    if channel_id != expected_id:
        return False, None
    if channel_token != expected_token:
        return False, None
    if resource_id != expected_resource:
        return False, None
    return True, resource_state
