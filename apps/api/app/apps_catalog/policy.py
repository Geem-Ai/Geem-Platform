"""App Store workspace actions — permission-based (Phase 10C)."""

from __future__ import annotations

from enum import StrEnum

from app.workspaces.models import WorkspaceMembership
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import has_permission, require_permission


class AppStoreAction(StrEnum):
    BROWSE_CATALOG = "browse_app_catalog"
    VIEW_INSTALLATIONS = "view_app_installations"
    INSTALL_APP = "install_app"
    UNINSTALL_APP = "uninstall_app"
    CONNECT_APP = "connect_app"


def require_browse(membership: WorkspaceMembership) -> None:
    require_permission(membership, WorkspacePermission.APPS_VIEW)


def require_manage_apps(membership: WorkspaceMembership) -> None:
    require_permission(membership, WorkspacePermission.APPS_MANAGE)


def require_connect_apps(membership: WorkspaceMembership) -> None:
    require_permission(membership, WorkspacePermission.APPS_CONNECT)


def can_manage_apps(membership: WorkspaceMembership) -> bool:
    return has_permission(membership, WorkspacePermission.APPS_MANAGE)


def can_connect_apps(membership: WorkspaceMembership) -> bool:
    return has_permission(membership, WorkspacePermission.APPS_CONNECT)
