"""Expert authorization (Phase 10C) — maps ExpertAction → WorkspacePermission."""

from __future__ import annotations

from enum import StrEnum

from app.workspaces.models import WorkspaceMembership
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import has_permission, require_permission


class ExpertAction(StrEnum):
    VIEW = "view_expert"
    USE = "use_expert"
    CREATE = "create_expert"
    UPDATE = "update_expert"
    DELETE = "delete_expert"
    MANAGE_KNOWLEDGE = "manage_expert_knowledge"


_ACTION_PERMISSION: dict[ExpertAction, WorkspacePermission] = {
    ExpertAction.VIEW: WorkspacePermission.EXPERTS_VIEW,
    ExpertAction.USE: WorkspacePermission.EXPERTS_USE,
    ExpertAction.CREATE: WorkspacePermission.EXPERTS_CREATE,
    ExpertAction.UPDATE: WorkspacePermission.EXPERTS_UPDATE,
    ExpertAction.DELETE: WorkspacePermission.EXPERTS_DELETE,
    ExpertAction.MANAGE_KNOWLEDGE: WorkspacePermission.EXPERTS_MANAGE_KNOWLEDGE,
}

_MANAGE_ACTIONS = frozenset(
    {
        ExpertAction.CREATE,
        ExpertAction.UPDATE,
        ExpertAction.DELETE,
        ExpertAction.MANAGE_KNOWLEDGE,
    }
)


class ExpertPolicy:
    @staticmethod
    def permission_for(action: ExpertAction) -> WorkspacePermission:
        return _ACTION_PERMISSION[action]

    @classmethod
    def can(cls, membership: WorkspaceMembership, action: ExpertAction) -> bool:
        return has_permission(membership, cls.permission_for(action))

    @classmethod
    def require(cls, membership: WorkspaceMembership, action: ExpertAction) -> None:
        require_permission(membership, cls.permission_for(action))

    @classmethod
    def can_manage_workspace_experts(cls, membership: WorkspaceMembership) -> bool:
        return cls.can(membership, ExpertAction.CREATE)

    @staticmethod
    def require_platform_admin(platform_role: str | None) -> None:
        from app.platform_admin.authz import require_platform_admin_role

        require_platform_admin_role(platform_role)

    @staticmethod
    def is_manage_action(action: ExpertAction) -> bool:
        return action in _MANAGE_ACTIONS
