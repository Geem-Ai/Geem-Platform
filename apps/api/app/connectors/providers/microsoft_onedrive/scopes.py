"""Microsoft OneDrive / Graph OAuth scopes (Phase 9E)."""

from __future__ import annotations

# Least-privilege delegated scopes for work/school OneDrive read + sync.
ONEDRIVE_SCOPES: tuple[str, ...] = (
    "openid",
    "profile",
    "offline_access",
    "User.Read",
    "Files.Read",
)

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


def oauth_scope_string() -> str:
    return " ".join(ONEDRIVE_SCOPES)
