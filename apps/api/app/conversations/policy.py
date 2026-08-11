"""Conversation authorization (Phase 4A).

Conversations are private to the owning user inside the current Workspace.
Any Workspace member may create/list/manage *their own* conversations; there is
no cross-user visibility within the Workspace for Phase 4.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import WorkspaceRole


class ConversationAction(StrEnum):
    CREATE = "create_conversation"
    VIEW = "view_conversation"
    UPDATE = "update_conversation"
    DELETE = "delete_conversation"
    LIST_MESSAGES = "list_conversation_messages"


# All tenant roles may use Chat with their own threads.
_ROLE_PERMISSIONS: dict[WorkspaceRole, frozenset[ConversationAction]] = {
    WorkspaceRole.OWNER: frozenset(ConversationAction),
    WorkspaceRole.ADMIN: frozenset(ConversationAction),
    WorkspaceRole.MEMBER: frozenset(ConversationAction),
}


class ConversationPolicy:
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
    def can(cls, role: str | WorkspaceRole, action: ConversationAction) -> bool:
        parsed = cls.parse_role(role)
        return action in _ROLE_PERMISSIONS[parsed]

    @classmethod
    def require(cls, role: str | WorkspaceRole, action: ConversationAction) -> None:
        if not cls.can(role, action):
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                f"Role '{role}' cannot perform '{action.value}'.",
                details={"required_action": action.value, "role": str(role)},
            )
