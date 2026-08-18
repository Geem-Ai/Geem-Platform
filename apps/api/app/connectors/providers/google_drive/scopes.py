"""Google Drive OAuth scopes (Phase 9D)."""

from __future__ import annotations

OPENID_SCOPES: tuple[str, ...] = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
)

DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

SCOPE_MODE_SELECTED_FILES = "selected_files"
SCOPE_MODE_READONLY = "readonly"

# consent → refresh_token; select_account → user can pick a different Google email.
GOOGLE_OAUTH_PROMPT = "consent select_account"


def scopes_for_mode(mode: str | None) -> list[str]:
    normalized = (mode or SCOPE_MODE_SELECTED_FILES).strip().lower()
    drive = (
        DRIVE_READONLY_SCOPE
        if normalized == SCOPE_MODE_READONLY
        else DRIVE_FILE_SCOPE
    )
    return [*OPENID_SCOPES, drive]


def requires_reauthorization(granted_scopes: list[str] | str | None, mode: str | None) -> bool:
    """True when granted scopes do not cover the configured mode."""
    if granted_scopes is None:
        return True
    if isinstance(granted_scopes, str):
        granted = {s.strip() for s in granted_scopes.split() if s.strip()}
    else:
        granted = {str(s).strip() for s in granted_scopes if str(s).strip()}
    required = set(scopes_for_mode(mode))
    # openid/profile/email variants may appear with or without full URLs
    # — require the Drive scope specifically.
    drive_required = (
        DRIVE_READONLY_SCOPE
        if (mode or SCOPE_MODE_SELECTED_FILES).strip().lower() == SCOPE_MODE_READONLY
        else DRIVE_FILE_SCOPE
    )
    return drive_required not in granted and not required.issubset(granted)
