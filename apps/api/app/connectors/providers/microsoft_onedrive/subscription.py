"""Microsoft Graph change notification subscriptions (Phase 9E)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

# Graph max for driveItem subscriptions is 42,300 minutes (~29.4 days).
# Stay below the documented maximum with a configurable default.
DEFAULT_SUBSCRIPTION_MINUTES = 4000  # ~2.7 days
RENEW_WITHIN_HOURS = 24


def webhook_notification_url(routing_token: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    base = (settings.app_url or "").rstrip("/")
    return f"{base}/api/connectors/webhooks/microsoft_onedrive/{routing_token}"


def subscription_resource(drive_id: str) -> str:
    """Subscribe to the drive root hierarchy (not per-file)."""
    return f"/drives/{drive_id}/root"


def new_client_state() -> str:
    return secrets.token_urlsafe(32)


def subscription_needs_renewal(sync_state: dict[str, Any] | None) -> bool:
    state = sync_state or {}
    sub = state.get("graph_subscription")
    if not isinstance(sub, dict):
        return True
    exp_raw = sub.get("expiration") or sub.get("expirationDateTime")
    if not exp_raw:
        return True
    try:
        exp = datetime.fromisoformat(str(exp_raw).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return exp <= datetime.now(timezone.utc) + timedelta(hours=RENEW_WITHIN_HOURS)


def desired_expiration(
    settings: Settings | None = None,
) -> datetime:
    settings = settings or get_settings()
    minutes = int(
        getattr(settings, "microsoft_onedrive_subscription_minutes", None)
        or DEFAULT_SUBSCRIPTION_MINUTES
    )
    # Cap below Graph maximum (42300).
    minutes = max(60, min(minutes, 40_000))
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def ensure_subscription(
    client: MicrosoftOneDriveClient,
    *,
    sync_state: dict[str, Any],
    drive_id: str,
    routing_token: str,
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    state = dict(sync_state or {})
    sub = state.get("graph_subscription")
    if isinstance(sub, dict) and sub.get("id") and not force:
        if not subscription_needs_renewal(state):
            return state
        try:
            renewed = client.renew_subscription(
                subscription_id=str(sub["id"]),
                expiration_datetime=desired_expiration(settings)
                .isoformat()
                .replace("+00:00", "Z"),
            )
            state["graph_subscription"] = {
                "id": renewed.get("id") or sub.get("id"),
                "expiration": renewed.get("expirationDateTime")
                or sub.get("expiration"),
                "resource": renewed.get("resource")
                or sub.get("resource")
                or subscription_resource(drive_id),
                "client_state": sub.get("client_state"),
            }
            return state
        except AppError as exc:
            if exc.category == ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED:
                raise
            # Fall through to recreate.
            pass

    client_state = (
        str(sub.get("client_state"))
        if isinstance(sub, dict) and sub.get("client_state")
        else new_client_state()
    )
    created = client.create_subscription(
        resource=subscription_resource(drive_id),
        notification_url=webhook_notification_url(routing_token, settings),
        client_state=client_state,
        expiration_datetime=desired_expiration(settings)
        .isoformat()
        .replace("+00:00", "Z"),
        change_type="updated",
    )
    state["graph_subscription"] = {
        "id": created.get("id"),
        "expiration": created.get("expirationDateTime"),
        "resource": created.get("resource") or subscription_resource(drive_id),
        "client_state": client_state,
    }
    state["drive_id"] = drive_id
    return state


def decode_validation_token(raw: str | None) -> str | None:
    if raw is None:
        return None
    # Graph may URL-encode; decode once (do not interpret structure).
    return unquote(raw)


def validate_notification_client_state(
    *,
    notification: dict[str, Any],
    sync_state: dict[str, Any] | None,
) -> bool:
    sub = (sync_state or {}).get("graph_subscription")
    if not isinstance(sub, dict):
        return False
    expected = sub.get("client_state")
    got = notification.get("clientState")
    if not expected or not got:
        return False
    return secrets.compare_digest(str(expected), str(got))
