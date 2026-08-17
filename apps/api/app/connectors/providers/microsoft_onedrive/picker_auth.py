"""File Picker v8 SharePoint-resource token helpers (Phase 9E).

Picker bootstrap and authenticate commands need SharePoint-host audience tokens,
not Graph tokens. Refresh-token rotation from those exchanges must be persisted
without replacing the connection's Graph access_token.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def picker_site_root(web_url: str) -> str:
    """Normalize a drive webUrl to ``https://{host}`` for File Picker v8."""
    raw = (web_url or "").strip().rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return raw


_PERSONAL_PICKER_HOST_SUFFIXES = (
    "onedrive.live.com",
    "microsoftpersonalcontent.com",
    "live.com",
)


def is_personal_onedrive_host(
    *,
    web_url: str | None = None,
    drive_type: str | None = None,
) -> bool:
    """True when the connected drive is personal MSA (File Picker v8 unsupported)."""
    dtype = (drive_type or "").strip().lower()
    if dtype == "personal":
        return True
    host = (urlsplit((web_url or "").strip()).netloc or "").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _PERSONAL_PICKER_HOST_SUFFIXES)


def assert_work_school_picker_supported(
    *,
    web_url: str | None,
    drive_type: str | None = None,
) -> None:
    """Fail closed for personal MSA — Picker v8 needs ODSP SharePoint-audience tokens."""
    if is_personal_onedrive_host(web_url=web_url, drive_type=drive_type):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Personal Microsoft accounts are not supported for File Picker. "
            "Connect a work or school OneDrive account.",
            details={"drive_type": drive_type or None, "host": (urlsplit(web_url or "").netloc or None)},
        )


def resolve_picker_base_url(
    *,
    sync_state: dict[str, Any],
    credentials: dict[str, Any],
    settings: Settings,
    access_token: str,
) -> tuple[str, dict[str, Any]]:
    """Return (picker_base, updated_sync_state). Fail closed if drive URL unknown."""
    state = dict(sync_state or {})
    base_url = str(
        state.get("drive_web_url") or credentials.get("drive_web_url") or ""
    ).strip().rstrip("/")
    if not base_url:
        tenant = str(credentials.get("tenant_id") or settings.microsoft_onedrive_tenant)
        client = MicrosoftOneDriveClient(
            settings=settings, access_token=access_token, tenant=tenant
        )
        try:
            drive = client.get_drive()
            base_url = str(drive.get("webUrl") or "").rstrip("/")
            if drive.get("id"):
                state["drive_id"] = drive["id"]
                state["drive_type"] = drive.get("driveType")
                state["drive_web_url"] = base_url
        finally:
            client.close()
    if not base_url:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_SYNC_FAILED,
            "Connected OneDrive web URL could not be resolved.",
        )
    picker_base = picker_site_root(base_url)
    if not picker_base.startswith("https://"):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Connected OneDrive host is not a supported https origin.",
        )
    drive_type = str(
        state.get("drive_type") or credentials.get("drive_type") or ""
    )
    assert_work_school_picker_supported(
        web_url=picker_base, drive_type=drive_type
    )
    state["drive_web_url"] = state.get("drive_web_url") or base_url
    return picker_base, state


def assert_picker_resource_allowed(
    *,
    resource: str,
    expected_web_url: str | None,
) -> str:
    """Fail closed unless resource host matches the connected OneDrive host."""
    resource = (resource or "").strip().rstrip("/")
    if not resource.startswith("https://"):
        raise AppError(ErrorCategory.VALIDATION, "Invalid picker resource.")
    expected = (expected_web_url or "").strip()
    expected_host = (urlsplit(expected).netloc or "").lower() if expected else ""
    if not expected_host:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Connected OneDrive host is not resolved; cannot mint picker tokens.",
        )
    resource_host = (urlsplit(resource).netloc or "").lower()
    if resource_host != expected_host:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Picker resource is not the connected OneDrive.",
        )
    return resource


def persist_rotated_refresh_token(
    cred_svc: ConnectorCredentialService,
    connection: AppConnection,
    credentials: dict[str, Any],
    token_payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist a rotated refresh_token only — never replace Graph access_token."""
    new_rt = token_payload.get("refresh_token")
    if not new_rt or new_rt == credentials.get("refresh_token"):
        return credentials
    updated = dict(credentials)
    updated["refresh_token"] = str(new_rt)
    # Keep Graph access token / expiry unchanged.
    from app.connectors.oauth_tokens import parse_expires_at

    cred_svc.set_credentials(
        connection,
        updated,
        expires_at=parse_expires_at(updated),
        merge_refresh=True,
    )
    return updated


def mint_picker_resource_token(
    *,
    db: Session,
    connection: AppConnection,
    credentials: dict[str, Any],
    resource: str,
    settings: Settings,
    sync_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Mint SharePoint-audience token; return (token_payload, updated_credentials)."""
    cred_svc = ConnectorCredentialService(db, settings=settings)
    state = sync_state if sync_state is not None else (cred_svc.get_sync_state(connection) or {})
    expected = str(state.get("drive_web_url") or credentials.get("drive_web_url") or "")
    drive_type = str(state.get("drive_type") or credentials.get("drive_type") or "")
    assert_work_school_picker_supported(web_url=expected, drive_type=drive_type)
    allowed = assert_picker_resource_allowed(
        resource=resource, expected_web_url=expected
    )
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
            "Microsoft OneDrive refresh token is missing.",
        )
    tenant = str(credentials.get("tenant_id") or settings.microsoft_onedrive_tenant)
    client = MicrosoftOneDriveClient(settings=settings, tenant=tenant)
    try:
        token_payload = client.acquire_resource_token(
            refresh_token=str(refresh_token),
            resource=allowed,
        )
    finally:
        client.close()
    updated = persist_rotated_refresh_token(
        cred_svc, connection, credentials, token_payload
    )
    return token_payload, updated
