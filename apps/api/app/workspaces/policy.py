from __future__ import annotations

from enum import StrEnum

from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import WorkspaceRole


class WorkspaceAction(StrEnum):
    READ_WORKSPACE = "read_workspace"
    UPDATE_WORKSPACE = "update_workspace"
    DELETE_WORKSPACE = "delete_workspace"
    VIEW_MEMBERS = "view_members"
    MANAGE_MEMBERS = "manage_members"
    CHANGE_MEMBER_ROLES = "change_member_roles"
    PROMOTE_TO_OWNER = "promote_to_owner"
    # Documents (Phase 2A) — members can manage knowledge in their workspace
    LIST_DOCUMENTS = "list_documents"
    READ_DOCUMENT = "read_document"
    UPLOAD_DOCUMENT = "upload_document"
    DELETE_DOCUMENT = "delete_document"
    REPROCESS_DOCUMENT = "reprocess_document"
    # API keys (Phase 7A) — owner/admin only
    MANAGE_API_KEYS = "manage_api_keys"


_DOCUMENT_ACTIONS = frozenset(
    {
        WorkspaceAction.LIST_DOCUMENTS,
        WorkspaceAction.READ_DOCUMENT,
        WorkspaceAction.UPLOAD_DOCUMENT,
        WorkspaceAction.DELETE_DOCUMENT,
        WorkspaceAction.REPROCESS_DOCUMENT,
    }
)


# Role matrix (Phase 1A + 2A documents). Admins cannot promote to owner unless explicitly allowed later.
_ROLE_PERMISSIONS: dict[WorkspaceRole, frozenset[WorkspaceAction]] = {
    WorkspaceRole.OWNER: frozenset(
        {
            WorkspaceAction.READ_WORKSPACE,
            WorkspaceAction.UPDATE_WORKSPACE,
            WorkspaceAction.DELETE_WORKSPACE,
            WorkspaceAction.VIEW_MEMBERS,
            WorkspaceAction.MANAGE_MEMBERS,
            WorkspaceAction.CHANGE_MEMBER_ROLES,
            WorkspaceAction.PROMOTE_TO_OWNER,
            WorkspaceAction.MANAGE_API_KEYS,
            *_DOCUMENT_ACTIONS,
        }
    ),
    WorkspaceRole.ADMIN: frozenset(
        {
            WorkspaceAction.READ_WORKSPACE,
            WorkspaceAction.UPDATE_WORKSPACE,
            WorkspaceAction.VIEW_MEMBERS,
            WorkspaceAction.MANAGE_MEMBERS,
            WorkspaceAction.CHANGE_MEMBER_ROLES,
            WorkspaceAction.MANAGE_API_KEYS,
            *_DOCUMENT_ACTIONS,
        }
    ),
    WorkspaceRole.MEMBER: frozenset(
        {
            WorkspaceAction.READ_WORKSPACE,
            WorkspaceAction.VIEW_MEMBERS,
            *_DOCUMENT_ACTIONS,
        }
    ),
}


class WorkspacePolicy:
    """Centralized workspace authorization. Do not scatter role string checks in routes."""

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
    def can(cls, role: str | WorkspaceRole, action: WorkspaceAction) -> bool:
        parsed = cls.parse_role(role)
        return action in _ROLE_PERMISSIONS[parsed]

    @classmethod
    def require(cls, role: str | WorkspaceRole, action: WorkspaceAction) -> None:
        if not cls.can(role, action):
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                f"Role '{role}' cannot perform '{action.value}'.",
                details={"required_action": action.value, "role": str(role)},
            )

    @classmethod
    def require_at_least(cls, role: str | WorkspaceRole, minimum: WorkspaceRole) -> None:
        order = {WorkspaceRole.MEMBER: 1, WorkspaceRole.ADMIN: 2, WorkspaceRole.OWNER: 3}
        parsed = cls.parse_role(role)
        if order[parsed] < order[minimum]:
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                f"Requires at least '{minimum.value}' role.",
                details={"role": parsed.value, "minimum": minimum.value},
            )
