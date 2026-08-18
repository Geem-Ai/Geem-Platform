"""Central workspace authorization (Phase 10C).

All HTTP/domain permission checks must go through this module. Controllers must
not join ``membership.workspace_role.permissions`` themselves.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, object_session

from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import WorkspaceMembership, WorkspaceRoleDef
from app.workspaces.permissions import (
    ALL_PERMISSION_KEYS,
    WorkspacePermission,
    permission_key,
)


def _resolve_role(membership: WorkspaceMembership) -> WorkspaceRoleDef | None:
    role = membership.workspace_role
    if role is not None:
        return role
    session = object_session(membership)
    if session is None or membership.role_id is None:
        return None
    return session.get(WorkspaceRoleDef, membership.role_id)


def get_effective_permissions(membership: WorkspaceMembership) -> frozenset[str]:
    """Resolve permission keys for a membership. Owner implies the full catalog."""
    role = _resolve_role(membership)
    if role is None:
        return frozenset()
    if role.is_owner_role:
        return ALL_PERMISSION_KEYS
    return frozenset(link.permission.key for link in role.permission_links)


def has_permission(
    membership: WorkspaceMembership,
    permission: WorkspacePermission | str,
) -> bool:
    key = permission_key(permission)
    return key in get_effective_permissions(membership)


def require_permission(
    membership: WorkspaceMembership,
    permission: WorkspacePermission | str,
) -> None:
    key = permission_key(permission)
    if not has_permission(membership, key):
        raise AppError(
            ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
            f"Missing required permission '{key}'.",
            details={
                "required_permission": key,
                "role_id": str(membership.role_id),
            },
        )


def is_owner_membership(membership: WorkspaceMembership) -> bool:
    role = _resolve_role(membership)
    return bool(role is not None and role.is_owner_role)


class PermissionService:
    """DB-backed helpers for authorization resolution."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_effective_permissions(self, membership: WorkspaceMembership) -> frozenset[str]:
        return get_effective_permissions(membership)

    def has_permission(
        self,
        membership: WorkspaceMembership,
        permission: WorkspacePermission | str,
    ) -> bool:
        return has_permission(membership, permission)

    def require_permission(
        self,
        membership: WorkspaceMembership,
        permission: WorkspacePermission | str,
    ) -> None:
        require_permission(membership, permission)
