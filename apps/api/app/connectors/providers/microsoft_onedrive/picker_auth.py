"""File Picker v8 token helpers (Phase 9E / 9E.1).

Work/school: SharePoint-host audience tokens + ODSP FilePicker.aspx.
Personal MSA: OneDrive.ReadOnly + https://onedrive.live.com/picker.

Refresh-token rotation from those exchanges is persisted without replacing the
connection's Graph access_token.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection
from app.connectors.providers.microsoft_onedrive.client import MicrosoftOneDriveClient
from app.connectors.providers.microsoft_onedrive.scopes import (
    ACCOUNT_KIND_PERSONAL,
    ACCOUNT_KIND_WORK_SCHOOL,
    PERSONAL_PICKER_BASE_URL,
    auth_tenant_for_account_kind,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

AccountKind = Literal["personal", "work_school"]

_PERSONAL_PICKER_HOSTS = frozenset(
    {
        "onedrive.live.com",
        "my.microsoftpersonalcontent.com",
    }
)
_PERSONAL_PICKER_HOST_SUFFIXES = (
    ".onedrive.live.com",
    ".microsoftpersonalcontent.com",
)

# Hosts personal File Picker v8 may send in ``authenticate.resource``.
# ``api.onedrive.com`` is required — the picker loads drive metadata there.
_PERSONAL_PICKER_AUTH_HOSTS = frozenset(
    {
        "onedrive.live.com",
        "api.onedrive.com",
        "my.microsoftpersonalcontent.com",
        "skyapi.onedrive.live.com",
    }
)


def _is_allowed_personal_picker_host(host: str) -> bool:
    h = (host or "").lower()
    if not h:
        return False
    if h in _PERSONAL_PICKER_AUTH_HOSTS:
        return True
    if any(h.endswith(suffix) for suffix in _PERSONAL_PICKER_HOST_SUFFIXES):
        return True
    if h == "docs.live.net" or h.endswith(".docs.live.net"):
        return True
    return False


def picker_site_root(web_url: str) -> str:
    """Normalize a drive webUrl to ``https://{host}`` for File Picker v8."""
    raw = (web_url or "").strip().rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return raw


def is_personal_onedrive_host(
    *,
    web_url: str | None = None,
    drive_type: str | None = None,
) -> bool:
    """True when the connected drive is personal MSA."""
    dtype = (drive_type or "").strip().lower()
    if dtype == "personal":
        return True
    host = (urlsplit((web_url or "").strip()).netloc or "").lower()
    if not host:
        return False
    if host in _PERSONAL_PICKER_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _PERSONAL_PICKER_HOST_SUFFIXES)


def classify_account_kind(
    *,
    web_url: str | None = None,
    drive_type: str | None = None,
    explicit: str | None = None,
) -> AccountKind:
    """Resolve ``personal`` vs ``work_school`` from drive metadata."""
    raw = (explicit or "").strip().lower()
    if raw in {ACCOUNT_KIND_PERSONAL, ACCOUNT_KIND_WORK_SCHOOL}:
        return raw  # type: ignore[return-value]
    if is_personal_onedrive_host(web_url=web_url, drive_type=drive_type):
        return ACCOUNT_KIND_PERSONAL  # type: ignore[return-value]
    return ACCOUNT_KIND_WORK_SCHOOL  # type: ignore[return-value]


def apply_account_kind_fields(
    target: dict[str, Any],
    *,
    web_url: str | None,
    drive_type: str | None,
    settings_tenant: str,
    explicit: str | None = None,
) -> AccountKind:
    """Set account_kind + auth_tenant on credentials or sync_state dict."""
    kind = classify_account_kind(
        web_url=web_url, drive_type=drive_type, explicit=explicit
    )
    target["account_kind"] = kind
    # Prefer consumers for personal; do not keep a stale non-consumers auth_tenant.
    if kind == ACCOUNT_KIND_PERSONAL:
        target["auth_tenant"] = "consumers"
    else:
        stored = str(target.get("auth_tenant") or "").strip() or None
        # Drop consumers leftover if this connection is work/school.
        if stored in {None, "", "consumers"}:
            stored = None
        target["auth_tenant"] = auth_tenant_for_account_kind(
            account_kind=kind,
            settings_tenant=settings_tenant,
            stored_auth_tenant=stored,
        )
    return kind


def resolve_picker_base_url(
    *,
    sync_state: dict[str, Any],
    credentials: dict[str, Any],
    settings: Settings,
    access_token: str,
) -> tuple[str, dict[str, Any], AccountKind]:
    """Return (picker_base, updated_sync_state, account_kind)."""
    state = dict(sync_state or {})
    base_url = str(
        state.get("drive_web_url") or credentials.get("drive_web_url") or ""
    ).strip().rstrip("/")
    if not base_url:
        tenant = str(
            credentials.get("auth_tenant")
            or credentials.get("tenant_id")
            or settings.microsoft_onedrive_tenant
        )
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
    if not base_url.startswith("https://") and not picker_site_root(base_url).startswith(
        "https://"
    ):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Connected OneDrive host is not a supported https origin.",
        )

    drive_type = str(state.get("drive_type") or credentials.get("drive_type") or "")
    explicit = str(state.get("account_kind") or credentials.get("account_kind") or "")
    kind = apply_account_kind_fields(
        state,
        web_url=base_url,
        drive_type=drive_type,
        settings_tenant=settings.microsoft_onedrive_tenant,
        explicit=explicit or None,
    )
    state["drive_web_url"] = state.get("drive_web_url") or base_url

    if kind == ACCOUNT_KIND_PERSONAL:
        return PERSONAL_PICKER_BASE_URL, state, kind

    picker_base = picker_site_root(base_url)
    if not picker_base.startswith("https://"):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Connected OneDrive host is not a supported https origin.",
        )
    return picker_base, state, kind


def assert_picker_resource_allowed(
    *,
    resource: str,
    expected_web_url: str | None,
    account_kind: AccountKind,
) -> str:
    """Fail closed unless resource host matches the account kind allowlist."""
    resource = (resource or "").strip().rstrip("/")
    if not resource.startswith("https://"):
        raise AppError(ErrorCategory.VALIDATION, "Invalid picker resource.")
    resource_host = (urlsplit(resource).netloc or "").lower()

    if account_kind == ACCOUNT_KIND_PERSONAL:
        # Picker authenticate may send onedrive.live.com, api.onedrive.com,
        # or the personal content / Live host — not Graph.
        if not _is_allowed_personal_picker_host(resource_host):
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
                "Picker resource is not a personal OneDrive host.",
                details={"resource_host": resource_host or None},
            )
        return resource

    expected = (expected_web_url or "").strip()
    expected_host = (urlsplit(expected).netloc or "").lower() if expected else ""
    if not expected_host:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED,
            "Connected OneDrive host is not resolved; cannot mint picker tokens.",
        )
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
    account_kind: AccountKind | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Mint picker token for the connection's account kind."""
    cred_svc = ConnectorCredentialService(db, settings=settings)
    state = (
        sync_state
        if sync_state is not None
        else (cred_svc.get_sync_state(connection) or {})
    )
    drive_url = str(state.get("drive_web_url") or credentials.get("drive_web_url") or "")
    drive_type = str(state.get("drive_type") or credentials.get("drive_type") or "")
    kind = account_kind or classify_account_kind(
        web_url=drive_url,
        drive_type=drive_type,
        explicit=str(state.get("account_kind") or credentials.get("account_kind") or ""),
    )

    if kind == ACCOUNT_KIND_PERSONAL:
        allowed = assert_picker_resource_allowed(
            resource=resource or PERSONAL_PICKER_BASE_URL,
            expected_web_url=PERSONAL_PICKER_BASE_URL,
            account_kind=kind,
        )
    else:
        allowed = assert_picker_resource_allowed(
            resource=resource,
            expected_web_url=drive_url,
            account_kind=kind,
        )

    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
            "Microsoft OneDrive refresh token is missing.",
        )

    tenant = auth_tenant_for_account_kind(
        account_kind=kind,
        settings_tenant=settings.microsoft_onedrive_tenant,
        stored_auth_tenant=str(
            credentials.get("auth_tenant") or state.get("auth_tenant") or ""
        )
        or None,
    )
    client = MicrosoftOneDriveClient(settings=settings, tenant=tenant)
    try:
        if kind == ACCOUNT_KIND_PERSONAL:
            # Graph authorize uses Files.Read only; Entra maps that to
            # OneDrive.ReadOnly for consumer picker mint. Do not require
            # OneDrive.ReadOnly in granted_scopes (mixing it on authorize
            # breaks MSA code exchange).
            token_payload = client.acquire_personal_picker_token(
                refresh_token=str(refresh_token)
            )
        else:
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


# Back-compat alias used by older tests/docs wording.
def assert_work_school_picker_supported(
    *,
    web_url: str | None,
    drive_type: str | None = None,
) -> None:
    """Deprecated no-op for work_school; personal is supported in 9E.1."""
    _ = web_url, drive_type
