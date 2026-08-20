"""Canonical Platform Admin authorization (independent of Workspace RBAC).

Workspace membership, workspace roles, and WorkspacePermission never grant
Platform Admin access. ``users.platform_role == admin`` is the only grant.
"""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory
from app.identity.models import PlatformRole, User, UserStatus


def require_platform_admin_role(platform_role: str | None) -> None:
    """Fail closed unless ``platform_role`` is the admin enum value."""
    if platform_role != PlatformRole.ADMIN.value:
        raise AppError(
            ErrorCategory.PLATFORM_ADMIN_REQUIRED,
            "Platform admin role required.",
        )


def require_platform_admin_user(user: User) -> User:
    """Authorize a loaded session user as Platform Admin.

    Callers must already have authenticated a human session (not an API key).
    Inactive / soft-deleted users are rejected by ``get_current_user`` before
    this runs; this function still fail-closes if those checks are skipped.
    """
    if user.deleted_at is not None or user.status != UserStatus.ACTIVE.value:
        raise AppError(ErrorCategory.UNAUTHORIZED, "User is not active.")
    require_platform_admin_role(user.platform_role)
    return user
