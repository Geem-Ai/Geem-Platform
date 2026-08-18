"""WorkspacePolicy — thin adapter over PermissionService (Phase 10C).

Legacy WorkspaceAction names map onto WorkspacePermission keys so existing
call sites migrate incrementally. Prefer WorkspacePermission + require_permission
in new code.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import WorkspaceMembership
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.rbac_service import has_permission, require_permission


class WorkspaceAction(StrEnum):
    READ_WORKSPACE = "read_workspace"
    UPDATE_WORKSPACE = "update_workspace"
    DELETE_WORKSPACE = "delete_workspace"
    VIEW_MEMBERS = "view_members"
    MANAGE_MEMBERS = "manage_members"
    CHANGE_MEMBER_ROLES = "change_member_roles"
    PROMOTE_TO_OWNER = "promote_to_owner"
    LIST_DOCUMENTS = "list_documents"
    READ_DOCUMENT = "read_document"
    DOWNLOAD_DOCUMENT = "download_document"
    UPLOAD_DOCUMENT = "upload_document"
    UPDATE_DOCUMENT = "update_document"
    DELETE_DOCUMENT = "delete_document"
    REPROCESS_DOCUMENT = "reprocess_document"
    MANAGE_API_KEYS = "manage_api_keys"
    VIEW_API_KEYS = "view_api_keys"
    CREATE_API_KEYS = "create_api_keys"
    REVOKE_API_KEYS = "revoke_api_keys"
    MANAGE_APPS = "manage_apps"
    VIEW_APPS = "view_apps"
    CONNECT_APPS = "connect_apps"
    VIEW_BILLING = "view_billing"
    MANAGE_BILLING = "manage_billing"
    PURCHASE_CREDITS = "purchase_credits"
    VIEW_API_USAGE = "view_api_usage"
    VIEW_ROLES = "view_roles"
    MANAGE_ROLES = "manage_roles"
    INVITE_MEMBERS = "invite_members"
    REMOVE_MEMBERS = "remove_members"
    USE_CHAT = "use_chat"


_ACTION_PERMISSION: dict[WorkspaceAction, WorkspacePermission] = {
    WorkspaceAction.READ_WORKSPACE: WorkspacePermission.WORKSPACE_VIEW,
    WorkspaceAction.UPDATE_WORKSPACE: WorkspacePermission.WORKSPACE_SETTINGS_MANAGE,
    WorkspaceAction.DELETE_WORKSPACE: WorkspacePermission.WORKSPACE_DELETE,
    WorkspaceAction.VIEW_MEMBERS: WorkspacePermission.MEMBERS_VIEW,
    WorkspaceAction.MANAGE_MEMBERS: WorkspacePermission.MEMBERS_REMOVE,
    WorkspaceAction.CHANGE_MEMBER_ROLES: WorkspacePermission.MEMBERS_UPDATE_ROLE,
    WorkspaceAction.PROMOTE_TO_OWNER: WorkspacePermission.MEMBERS_PROMOTE_OWNER,
    WorkspaceAction.LIST_DOCUMENTS: WorkspacePermission.STORAGE_VIEW,
    WorkspaceAction.READ_DOCUMENT: WorkspacePermission.STORAGE_VIEW,
    WorkspaceAction.DOWNLOAD_DOCUMENT: WorkspacePermission.STORAGE_DOWNLOAD,
    WorkspaceAction.UPLOAD_DOCUMENT: WorkspacePermission.STORAGE_UPLOAD,
    WorkspaceAction.UPDATE_DOCUMENT: WorkspacePermission.STORAGE_UPDATE,
    WorkspaceAction.DELETE_DOCUMENT: WorkspacePermission.STORAGE_DELETE,
    WorkspaceAction.REPROCESS_DOCUMENT: WorkspacePermission.STORAGE_REPROCESS,
    WorkspaceAction.MANAGE_API_KEYS: WorkspacePermission.API_KEYS_VIEW,
    WorkspaceAction.VIEW_API_KEYS: WorkspacePermission.API_KEYS_VIEW,
    WorkspaceAction.CREATE_API_KEYS: WorkspacePermission.API_KEYS_CREATE,
    WorkspaceAction.REVOKE_API_KEYS: WorkspacePermission.API_KEYS_REVOKE,
    WorkspaceAction.MANAGE_APPS: WorkspacePermission.APPS_MANAGE,
    WorkspaceAction.VIEW_APPS: WorkspacePermission.APPS_VIEW,
    WorkspaceAction.CONNECT_APPS: WorkspacePermission.APPS_CONNECT,
    WorkspaceAction.VIEW_BILLING: WorkspacePermission.BILLING_VIEW,
    WorkspaceAction.MANAGE_BILLING: WorkspacePermission.BILLING_MANAGE,
    WorkspaceAction.PURCHASE_CREDITS: WorkspacePermission.BILLING_PURCHASE_CREDITS,
    WorkspaceAction.VIEW_API_USAGE: WorkspacePermission.API_USAGE_VIEW,
    WorkspaceAction.VIEW_ROLES: WorkspacePermission.ROLES_VIEW,
    WorkspaceAction.MANAGE_ROLES: WorkspacePermission.ROLES_MANAGE,
    WorkspaceAction.INVITE_MEMBERS: WorkspacePermission.MEMBERS_INVITE,
    WorkspaceAction.REMOVE_MEMBERS: WorkspacePermission.MEMBERS_REMOVE,
    WorkspaceAction.USE_CHAT: WorkspacePermission.CHAT_USE,
}


class WorkspacePolicy:
    """Centralized workspace authorization. Do not scatter role string checks in routes."""

    @staticmethod
    def permission_for(action: WorkspaceAction) -> WorkspacePermission:
        try:
            return _ACTION_PERMISSION[action]
        except KeyError as exc:
            raise AppError(
                ErrorCategory.VALIDATION,
                "Unknown workspace action.",
                details={"action": str(action)},
            ) from exc

    @classmethod
    def can(cls, membership: WorkspaceMembership, action: WorkspaceAction) -> bool:
        return has_permission(membership, cls.permission_for(action))

    @classmethod
    def require(cls, membership: WorkspaceMembership, action: WorkspaceAction) -> None:
        require_permission(membership, cls.permission_for(action))
