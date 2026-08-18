"""Geem-controlled workspace permission registry (Phase 10C).

Tenants assign these keys to workspace roles. They cannot invent new keys.
Display copy lives in workspace_web i18n (`name_key` / `description_key`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkspacePermission(StrEnum):
    WORKSPACE_VIEW = "workspace.view"
    WORKSPACE_DELETE = "workspace.delete"

    WORKSPACE_SETTINGS_VIEW = "workspace_settings.view"
    WORKSPACE_SETTINGS_MANAGE = "workspace_settings.manage"

    CHAT_USE = "chat.use"

    EXPERTS_VIEW = "experts.view"
    EXPERTS_USE = "experts.use"
    EXPERTS_CREATE = "experts.create"
    EXPERTS_UPDATE = "experts.update"
    EXPERTS_DELETE = "experts.delete"
    EXPERTS_MANAGE_KNOWLEDGE = "experts.manage_knowledge"

    STORAGE_VIEW = "storage.view"
    STORAGE_DOWNLOAD = "storage.download"
    STORAGE_UPLOAD = "storage.upload"
    STORAGE_UPDATE = "storage.update"
    STORAGE_DELETE = "storage.delete"
    STORAGE_REPROCESS = "storage.reprocess"

    APPS_VIEW = "apps.view"
    APPS_MANAGE = "apps.manage"
    APPS_CONNECT = "apps.connect"

    MEMBERS_VIEW = "members.view"
    MEMBERS_INVITE = "members.invite"
    MEMBERS_UPDATE_ROLE = "members.update_role"
    MEMBERS_REMOVE = "members.remove"
    MEMBERS_PROMOTE_OWNER = "members.promote_owner"

    ROLES_VIEW = "roles.view"
    ROLES_MANAGE = "roles.manage"

    API_KEYS_VIEW = "api_keys.view"
    API_KEYS_CREATE = "api_keys.create"
    API_KEYS_REVOKE = "api_keys.revoke"

    API_USAGE_VIEW = "api_usage.view"

    BILLING_VIEW = "billing.view"
    BILLING_MANAGE = "billing.manage"
    BILLING_PURCHASE_CREDITS = "billing.purchase_credits"


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    key: WorkspacePermission
    group_key: str
    name_key: str
    description_key: str
    owner_only: bool = False


def _spec(
    permission: WorkspacePermission,
    group: str,
    *,
    owner_only: bool = False,
) -> PermissionSpec:
    dotted = permission.value
    return PermissionSpec(
        key=permission,
        group_key=group,
        name_key=f"permissions.{dotted}.name",
        description_key=f"permissions.{dotted}.description",
        owner_only=owner_only,
    )


PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    _spec(WorkspacePermission.WORKSPACE_VIEW, "workspace"),
    _spec(WorkspacePermission.WORKSPACE_DELETE, "workspace", owner_only=True),
    _spec(WorkspacePermission.WORKSPACE_SETTINGS_VIEW, "workspace_settings"),
    _spec(WorkspacePermission.WORKSPACE_SETTINGS_MANAGE, "workspace_settings"),
    _spec(WorkspacePermission.CHAT_USE, "chat"),
    _spec(WorkspacePermission.EXPERTS_VIEW, "experts"),
    _spec(WorkspacePermission.EXPERTS_USE, "experts"),
    _spec(WorkspacePermission.EXPERTS_CREATE, "experts"),
    _spec(WorkspacePermission.EXPERTS_UPDATE, "experts"),
    _spec(WorkspacePermission.EXPERTS_DELETE, "experts"),
    _spec(WorkspacePermission.EXPERTS_MANAGE_KNOWLEDGE, "experts"),
    _spec(WorkspacePermission.STORAGE_VIEW, "storage"),
    _spec(WorkspacePermission.STORAGE_DOWNLOAD, "storage"),
    _spec(WorkspacePermission.STORAGE_UPLOAD, "storage"),
    _spec(WorkspacePermission.STORAGE_UPDATE, "storage"),
    _spec(WorkspacePermission.STORAGE_DELETE, "storage"),
    _spec(WorkspacePermission.STORAGE_REPROCESS, "storage"),
    _spec(WorkspacePermission.APPS_VIEW, "apps"),
    _spec(WorkspacePermission.APPS_MANAGE, "apps"),
    _spec(WorkspacePermission.APPS_CONNECT, "apps"),
    _spec(WorkspacePermission.MEMBERS_VIEW, "members"),
    _spec(WorkspacePermission.MEMBERS_INVITE, "members"),
    _spec(WorkspacePermission.MEMBERS_UPDATE_ROLE, "members"),
    _spec(WorkspacePermission.MEMBERS_REMOVE, "members"),
    _spec(WorkspacePermission.MEMBERS_PROMOTE_OWNER, "members", owner_only=True),
    _spec(WorkspacePermission.ROLES_VIEW, "roles"),
    _spec(WorkspacePermission.ROLES_MANAGE, "roles"),
    _spec(WorkspacePermission.API_KEYS_VIEW, "api_keys"),
    _spec(WorkspacePermission.API_KEYS_CREATE, "api_keys"),
    _spec(WorkspacePermission.API_KEYS_REVOKE, "api_keys"),
    _spec(WorkspacePermission.API_USAGE_VIEW, "api_usage"),
    _spec(WorkspacePermission.BILLING_VIEW, "billing"),
    _spec(WorkspacePermission.BILLING_MANAGE, "billing"),
    _spec(WorkspacePermission.BILLING_PURCHASE_CREDITS, "billing"),
)

PERMISSION_BY_KEY: dict[str, PermissionSpec] = {spec.key.value: spec for spec in PERMISSION_CATALOG}

ALL_PERMISSION_KEYS: frozenset[str] = frozenset(spec.key.value for spec in PERMISSION_CATALOG)
ASSIGNABLE_PERMISSION_KEYS: frozenset[str] = frozenset(
    spec.key.value for spec in PERMISSION_CATALOG if not spec.owner_only
)
OWNER_ONLY_PERMISSION_KEYS: frozenset[str] = frozenset(
    spec.key.value for spec in PERMISSION_CATALOG if spec.owner_only
)

# Overview is available to every default membership. Custom roles must include
# workspace.view explicitly; otherwise the user may only have a 403 shell.
OVERVIEW_PERMISSION = WorkspacePermission.WORKSPACE_VIEW

# Equivalent to Phase 10 member WorkspacePolicy + ExpertPolicy + unrestricted
# billing/usage/api-usage membership (those routers only required membership).
MEMBER_PERMISSION_KEYS: frozenset[str] = frozenset(
    {
        WorkspacePermission.WORKSPACE_VIEW.value,
        WorkspacePermission.WORKSPACE_SETTINGS_VIEW.value,
        WorkspacePermission.CHAT_USE.value,
        WorkspacePermission.EXPERTS_VIEW.value,
        WorkspacePermission.EXPERTS_USE.value,
        WorkspacePermission.STORAGE_VIEW.value,
        WorkspacePermission.STORAGE_DOWNLOAD.value,
        WorkspacePermission.STORAGE_UPLOAD.value,
        WorkspacePermission.STORAGE_UPDATE.value,
        WorkspacePermission.STORAGE_DELETE.value,
        WorkspacePermission.STORAGE_REPROCESS.value,
        WorkspacePermission.APPS_VIEW.value,
        WorkspacePermission.MEMBERS_VIEW.value,
        WorkspacePermission.BILLING_VIEW.value,
        WorkspacePermission.BILLING_MANAGE.value,
        WorkspacePermission.BILLING_PURCHASE_CREDITS.value,
        WorkspacePermission.API_USAGE_VIEW.value,
    }
)

# Equivalent to Phase 10 admin: member set plus mutations, minus owner-only ops.
ADMIN_PERMISSION_KEYS: frozenset[str] = MEMBER_PERMISSION_KEYS | frozenset(
    {
        WorkspacePermission.WORKSPACE_SETTINGS_MANAGE.value,
        WorkspacePermission.EXPERTS_CREATE.value,
        WorkspacePermission.EXPERTS_UPDATE.value,
        WorkspacePermission.EXPERTS_DELETE.value,
        WorkspacePermission.EXPERTS_MANAGE_KNOWLEDGE.value,
        WorkspacePermission.APPS_MANAGE.value,
        WorkspacePermission.APPS_CONNECT.value,
        WorkspacePermission.MEMBERS_INVITE.value,
        WorkspacePermission.MEMBERS_UPDATE_ROLE.value,
        WorkspacePermission.MEMBERS_REMOVE.value,
        WorkspacePermission.ROLES_VIEW.value,
        WorkspacePermission.ROLES_MANAGE.value,
        WorkspacePermission.API_KEYS_VIEW.value,
        WorkspacePermission.API_KEYS_CREATE.value,
        WorkspacePermission.API_KEYS_REVOKE.value,
    }
)


class SystemRoleKey(StrEnum):
    """Stable keys for seeded system roles. Display names are not used for authz."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


SYSTEM_ROLE_DISPLAY_NAMES: dict[str, str] = {
    SystemRoleKey.OWNER.value: "Owner",
    SystemRoleKey.ADMIN.value: "Administrator",
    SystemRoleKey.MEMBER.value: "Member",
}


def parse_permission_key(value: str) -> WorkspacePermission:
    spec = PERMISSION_BY_KEY.get(value)
    if spec is None:
        from app.core.errors import AppError, ErrorCategory

        raise AppError(
            ErrorCategory.UNKNOWN_PERMISSION,
            "Unknown permission key.",
            details={"permission": value},
        )
    return spec.key


def permission_key(value: WorkspacePermission | str) -> str:
    if isinstance(value, WorkspacePermission):
        return value.value
    return parse_permission_key(value).value
