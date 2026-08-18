"""Conversation authorization (Phase 10C).

Conversations are private to the owning user inside the current Workspace.
Any member with ``chat.use`` may manage *their own* conversations.
"""

from __future__ import annotations

from enum import StrEnum

from app.workspaces.models import WorkspaceMembership
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import has_permission, require_permission


class ConversationAction(StrEnum):
    CREATE = "create_conversation"
    VIEW = "view_conversation"
    UPDATE = "update_conversation"
    DELETE = "delete_conversation"
    LIST_MESSAGES = "list_conversation_messages"


class ConversationPolicy:
    @classmethod
    def can(cls, membership: WorkspaceMembership, action: ConversationAction) -> bool:
        _ = action
        return has_permission(membership, WorkspacePermission.CHAT_USE)

    @classmethod
    def require(cls, membership: WorkspaceMembership, action: ConversationAction) -> None:
        _ = action
        require_permission(membership, WorkspacePermission.CHAT_USE)
