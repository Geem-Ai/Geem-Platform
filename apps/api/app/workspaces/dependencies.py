from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.identity.dependencies import get_current_user, get_workspace_hint, require_workspace
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.policy import WorkspaceAction, WorkspacePolicy
from app.workspaces.rbac_service import require_permission
from app.workspaces.service import WorkspaceService


def get_workspace_service(db: Session = Depends(get_db)) -> WorkspaceService:
    return WorkspaceService(db)


def require_workspace_action(action: WorkspaceAction):
    """Dependency factory: resolve workspace and require a policy action."""

    def _dep(
        pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    ) -> tuple[Workspace, WorkspaceMembership]:
        workspace, membership = pair
        WorkspacePolicy.require(membership, action)
        return workspace, membership

    return _dep


def require_workspace_permission(permission: WorkspacePermission):
    """Dependency factory: resolve workspace and require a permission key."""

    def _dep(
        pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    ) -> tuple[Workspace, WorkspaceMembership]:
        workspace, membership = pair
        require_permission(membership, permission)
        return workspace, membership

    return _dep


# Re-exports for routers
__all__ = [
    "User",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceService",
    "WorkspaceAction",
    "WorkspacePolicy",
    "WorkspacePermission",
    "WorkspaceRole",
    "get_current_user",
    "get_workspace_hint",
    "get_workspace_service",
    "require_workspace",
    "require_workspace_action",
    "require_workspace_permission",
]
