"""Microsoft OneDrive / Graph OAuth scopes (Phase 9E / 9E.1)."""

from __future__ import annotations

# Least-privilege delegated scopes for OneDrive read + sync (Graph).
ONEDRIVE_SCOPES: tuple[str, ...] = (
    "openid",
    "profile",
    "offline_access",
    "User.Read",
    "Files.Read",
)

# Personal MSA File Picker v8 — Live Connect style scope (not a Graph permission tile).
PERSONAL_PICKER_SCOPE = "OneDrive.ReadOnly"

# Never request write / broad site scopes by default.
FORBIDDEN_DEFAULT_SCOPES: frozenset[str] = frozenset(
    {
        "Files.ReadWrite",
        "Files.Read.All",
        "Files.ReadWrite.All",
        "Sites.Read.All",
        "Sites.ReadWrite.All",
    }
)

ACCOUNT_KIND_PERSONAL = "personal"
ACCOUNT_KIND_WORK_SCHOOL = "work_school"

PERSONAL_PICKER_BASE_URL = "https://onedrive.live.com/picker"


def tenant_allows_personal_accounts(tenant: str | None) -> bool:
    """True when Entra tenant mode can issue MSA tokens (dual-account deploys)."""
    t = (tenant or "").strip().lower()
    return t in {"common", "consumers"}


def oauth_scopes_for_tenant(tenant: str | None) -> tuple[str, ...]:
    """Authorize / code-exchange scopes — Microsoft Graph only.

    Do **not** mix ``OneDrive.ReadOnly`` here. That Live Connect scope is a
    different resource; including it with Graph scopes breaks MSA token
    exchange (HTTP 400). Personal File Picker mints ``OneDrive.ReadOnly``
    separately via ``acquire_personal_picker_token`` (Entra maps consented
    Graph ``Files.Read`` for consumer picker tokens).
    """
    _ = tenant
    return ONEDRIVE_SCOPES


def oauth_scope_string(tenant: str | None = None) -> str:
    return " ".join(oauth_scopes_for_tenant(tenant))


def auth_tenant_for_account_kind(
    *,
    account_kind: str,
    settings_tenant: str,
    stored_auth_tenant: str | None = None,
) -> str:
    """Token endpoint tenant for Graph/picker refreshes."""
    if account_kind == ACCOUNT_KIND_PERSONAL:
        return "consumers"
    stored = (stored_auth_tenant or "").strip()
    if stored and stored != "consumers":
        return stored
    return (settings_tenant or "organizations").strip() or "organizations"
