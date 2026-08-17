"""Microsoft OneDrive credential refresh helpers (Phase 9E)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.oauth_tokens import (
    apply_token_response,
    credentials_need_refresh,
    expires_at_from_credentials,
    merge_token_response,
    parse_expires_at,
)
from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
from app.connectors.repository import ConnectorRepository
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

__all__ = [
    "apply_token_response",
    "credentials_need_refresh",
    "ensure_fresh_access",
    "expires_at_from_credentials",
    "merge_token_response",
    "parse_expires_at",
]


def ensure_fresh_access(
    db: Session,
    connection: AppConnection,
    credentials: dict[str, Any],
    settings: Settings | None = None,
    *,
    client: MicrosoftOneDriveClient | None = None,
) -> dict[str, Any]:
    """Refresh access token if expired/near-expiry; persist under row lock."""
    settings = settings or get_settings()
    if not credentials_need_refresh(credentials):
        return credentials

    if not credentials.get("refresh_token"):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
            "Microsoft OneDrive refresh token is missing.",
        )

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

    refresh_token = current.get("refresh_token")
    if not refresh_token:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
            "Microsoft OneDrive refresh token is missing.",
        )

    tenant = str(
        current.get("auth_tenant")
        or current.get("tenant_id")
        or settings.microsoft_onedrive_tenant
    )
    owned = client is None
    graph = client or MicrosoftOneDriveClient(settings=settings, tenant=tenant)
    try:
        token_payload = graph.refresh_access_token(refresh_token=str(refresh_token))
    finally:
        if owned:
            graph.close()

    refreshed = apply_token_response(current, token_payload)
    expires_at = parse_expires_at(refreshed)
    cred_svc.set_credentials(
        locked, refreshed, expires_at=expires_at, merge_refresh=True
    )
    db.flush()
    return refreshed
