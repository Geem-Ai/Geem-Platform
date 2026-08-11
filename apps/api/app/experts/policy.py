"""Centralized Expert authorization (Phase 3A).

Workspace role matrix (decision: Members may view/use; only Owner/Admin create/edit/delete/manage knowledge):

                    Owner   Admin   Member
View / Use            ✓       ✓       ✓
Create Expert         ✓       ✓       -
Edit Expert           ✓       ✓       -
Delete Expert         ✓       ✓       -
Manage knowledge      ✓       ✓       -

Platform Expert management requires ``platform_role=admin``, not Workspace Owner.

Quota / ``experts_included`` is Phase 5 — this policy answers role permission only.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.errors import AppError, ErrorCategory
from app.identity.models import PlatformRole
from app.workspaces.models import WorkspaceRole


class ExpertAction(StrEnum):
    VIEW = "view_expert"
    USE = "use_expert"
    CREATE = "create_expert"
    UPDATE = "update_expert"
    DELETE = "delete_expert"
    MANAGE_KNOWLEDGE = "manage_expert_knowledge"


_MANAGE_ACTIONS = frozenset(
    {
        ExpertAction.CREATE,
        ExpertAction.UPDATE,
        ExpertAction.DELETE,
        ExpertAction.MANAGE_KNOWLEDGE,
    }
)

_ROLE_PERMISSIONS: dict[WorkspaceRole, frozenset[ExpertAction]] = {
    WorkspaceRole.OWNER: frozenset(ExpertAction),
    WorkspaceRole.ADMIN: frozenset(ExpertAction),
    WorkspaceRole.MEMBER: frozenset({ExpertAction.VIEW, ExpertAction.USE}),
}


class ExpertPolicy:
    @staticmethod
    def parse_role(role: str | WorkspaceRole) -> WorkspaceRole:
        if isinstance(role, WorkspaceRole):
            return role
        try:
            return WorkspaceRole(role)
        except ValueError as exc:
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                "Unknown workspace role.",
            ) from exc

    @classmethod
    def can(cls, role: str | WorkspaceRole, action: ExpertAction) -> bool:
        parsed = cls.parse_role(role)
        return action in _ROLE_PERMISSIONS[parsed]

    @classmethod
    def require(cls, role: str | WorkspaceRole, action: ExpertAction) -> None:
        if not cls.can(role, action):
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                f"Role '{role}' cannot perform '{action.value}'.",
                details={"required_action": action.value, "role": str(role)},
            )

    @classmethod
    def can_manage_workspace_experts(cls, role: str | WorkspaceRole) -> bool:
        return cls.can(role, ExpertAction.CREATE)

    @staticmethod
    def require_platform_admin(platform_role: str | None) -> None:
        if platform_role != PlatformRole.ADMIN.value:
            raise AppError(
                ErrorCategory.PLATFORM_ADMIN_REQUIRED,
                "Platform admin role required.",
            )

    @staticmethod
    def is_manage_action(action: ExpertAction) -> bool:
        return action in _MANAGE_ACTIONS
