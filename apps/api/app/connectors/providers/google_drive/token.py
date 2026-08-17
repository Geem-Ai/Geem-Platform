"""Google Drive credential refresh helpers (Phase 9D)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.providers.google_drive.client import GoogleDriveClient
from app.connectors.repository import ConnectorRepository
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

# Refresh when fewer than this many seconds remain.
_REFRESH_SKEW_SECONDS = 120


def merge_token_response(
    old: dict[str, Any] | None, new: dict[str, Any]
) -> dict[str, Any]:
    """Merge OAuth token payloads — never overwrite refresh_token with null/missing."""
    merged: dict[str, Any] = dict(old or {})
    for key, value in new.items():
        if key == "refresh_token" and (value is None or value == ""):
            continue
        merged[key] = value
    # Preserve prior refresh_token when absent from new.
    if not merged.get("refresh_token") and old and old.get("refresh_token"):
        merged["refresh_token"] = old["refresh_token"]
    return merged


def _parse_expires_at(credentials: dict[str, Any]) -> datetime | None:
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


def credentials_need_refresh(credentials: dict[str, Any]) -> bool:
    if not credentials.get("access_token"):
        return True
    expires_at = _parse_expires_at(credentials)
    if expires_at is None:
        return False
    return expires_at <= datetime.now(timezone.utc) + timedelta(
        seconds=_REFRESH_SKEW_SECONDS
    )


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


def ensure_fresh_access(
    db: Session,
    connection: AppConnection,
    credentials: dict[str, Any],
    settings: Settings | None = None,
    *,
    client: GoogleDriveClient | None = None,
) -> dict[str, Any]:
    """Refresh access token if expired/near-expiry; persist under row lock."""
    settings = settings or get_settings()
    if not credentials_need_refresh(credentials):
        return credentials

    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise AppError(
            ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
            "Google Drive refresh token is missing.",
        )

    # Lock connection row for atomic credential update.
    repo = ConnectorRepository(db)
    locked = repo.get_connection(
        connection.workspace_id, connection.id, for_update=True
    )
    if locked is None:
        raise AppError(ErrorCategory.CONNECTOR_NOT_FOUND, "Connection not found.")

    cred_svc = ConnectorCredentialService(db, settings=settings)
    current = cred_svc.get_credentials(locked) or dict(credentials)
    if not credentials_need_refresh(current):
        return current

    owned = client is None
    drive = client or GoogleDriveClient(settings=settings)
    try:
        token_payload = drive.refresh_access_token(refresh_token=str(refresh_token))
    finally:
        if owned:
            drive.close()

    refreshed = apply_token_response(current, token_payload)
    expires_at = _parse_expires_at(refreshed)
    cred_svc.set_credentials(locked, refreshed, expires_at=expires_at, merge_refresh=True)
    db.flush()
    return refreshed


def expires_at_from_credentials(credentials: dict[str, Any]) -> datetime | None:
    return _parse_expires_at(credentials)
