"""App Store workspace actions — owner/admin mutate; members browse."""

from __future__ import annotations

from enum import StrEnum

from app.workspaces.models import WorkspaceRole
from app.workspaces.policy import WorkspaceAction, WorkspacePolicy


class AppStoreAction(StrEnum):
    BROWSE_CATALOG = "browse_app_catalog"
    VIEW_INSTALLATIONS = "view_app_installations"
    INSTALL_APP = "install_app"
    UNINSTALL_APP = "uninstall_app"


# Mapped onto WorkspaceAction for central role matrix.
# INSTALL/UNINSTALL → MANAGE_APPS; browse/view → READ_WORKSPACE.


def require_browse(role: str | WorkspaceRole) -> None:
    WorkspacePolicy.require(role, WorkspaceAction.READ_WORKSPACE)


def require_manage_apps(role: str | WorkspaceRole) -> None:
    WorkspacePolicy.require(role, WorkspaceAction.MANAGE_APPS)


def can_manage_apps(role: str | WorkspaceRole) -> bool:
    return WorkspacePolicy.can(role, WorkspaceAction.MANAGE_APPS)
