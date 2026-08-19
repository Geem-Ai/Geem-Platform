"""Workspace-scoped role CRUD (Phase 10C)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.audit import AuditAction, AuditEntityType, record_audit
from app.core.errors import AppError, ErrorCategory
from app.workspaces.invitation_repository import InvitationRepository
from app.workspaces.models import (
    Permission,
    WorkspaceInvitation,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceRolePermission,
)
from app.workspaces.permissions import (
    ASSIGNABLE_PERMISSION_KEYS,
    OWNER_ONLY_PERMISSION_KEYS,
    PERMISSION_CATALOG,
    parse_permission_key,
)
from app.workspaces.rbac_seed import normalize_role_name
from app.workspaces.rbac_service import require_permission
from app.workspaces.permissions import WorkspacePermission
from app.workspaces.repository import MembershipRepository, WorkspaceRepository
from app.workspaces.schemas import PermissionCatalogItemOut, RoleOut
from app.workspaces.service import WorkspaceService

UNSET = object()


class RoleService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.workspaces = WorkspaceRepository(db)
        self.memberships = MembershipRepository(db)
        self.invitations = InvitationRepository(db)
        self._workspace_svc = WorkspaceService(db)

    def list_catalog(self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID) -> list[PermissionCatalogItemOut]:
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.ROLES_VIEW)
        return [
            PermissionCatalogItemOut(
                key=spec.key.value,
                group=spec.group_key,
                name_key=spec.name_key,
                description_key=spec.description_key,
                owner_only=spec.owner_only,
            )
            for spec in PERMISSION_CATALOG
        ]

    def list_roles(self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID) -> list[RoleOut]:
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.ROLES_VIEW)
        rows = list(
            self.db.scalars(
                select(WorkspaceRoleDef)
                .options(
                    selectinload(WorkspaceRoleDef.permission_links).selectinload(
                        WorkspaceRolePermission.permission
                    )
                )
                .where(WorkspaceRoleDef.workspace_id == workspace_id)
                .order_by(
                    WorkspaceRoleDef.is_owner_role.desc(),
                    WorkspaceRoleDef.is_system.desc(),
                    WorkspaceRoleDef.created_at.asc(),
                )
            ).all()
        )
        counts = self._assignment_counts(workspace_id)
        return [self._to_out(row, assigned=counts.get(row.id, 0)) for row in rows]

    def get_role(
        self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID, role_id: uuid.UUID
    ) -> RoleOut:
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.ROLES_VIEW)
        role = self._get_role(workspace_id, role_id)
        return self._to_out(role, assigned=self._assignment_counts(workspace_id).get(role.id, 0))

    def create_role(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str,
        description: str | None,
        permission_keys: list[str],
    ) -> RoleOut:
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.ROLES_MANAGE)
        clean_name = self._validate_name(name)
        keys = self._validate_assignable_keys(permission_keys)
        role = WorkspaceRoleDef(
            workspace_id=workspace_id,
            name=clean_name,
            name_normalized=normalize_role_name(clean_name),
            description=(description or "").strip() or None,
            system_key=None,
            is_system=False,
            is_owner_role=False,
        )
        try:
            self.db.add(role)
            self.db.flush()
            self._replace_permissions(role, keys)
            record_audit(
                self.db,
                action=AuditAction.ROLE_CREATED,
                entity_type=AuditEntityType.ROLE,
                entity_id=role.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={"permission_keys": keys},
                allowlist=frozenset({"permission_keys"}),
            )
            self.db.commit()
            self.db.expire_all()
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_workspace_roles_workspace_name" in str(exc).lower():
                raise AppError(
                    ErrorCategory.ROLE_NAME_TAKEN,
                    "A role with this name already exists in the workspace.",
                ) from exc
            raise
        loaded = self._get_role(workspace_id, role.id)
        return self._to_out(loaded, assigned=0)

    def update_role(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        role_id: uuid.UUID,
        name: str | None,
        description: str | None | object,
        permission_keys: list[str] | None,
    ) -> RoleOut:
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.ROLES_MANAGE)
        role = self._get_role(workspace_id, role_id)
        if role.is_owner_role:
            raise AppError(
                ErrorCategory.ROLE_PROTECTED,
                "The Owner role cannot be edited.",
            )
        if role.is_system and name is not None and self._validate_name(name) != role.name:
            raise AppError(
                ErrorCategory.ROLE_PROTECTED,
                "System roles cannot be renamed.",
            )
        if name is not None:
            role.name = self._validate_name(name)
            role.name_normalized = normalize_role_name(role.name)
        if description is not UNSET:
            role.description = (description or "").strip() or None
        if permission_keys is not None:
            keys = self._validate_assignable_keys(permission_keys)
            self._replace_permissions(role, keys)
        try:
            record_audit(
                self.db,
                action=AuditAction.ROLE_UPDATED,
                entity_type=AuditEntityType.ROLE,
                entity_id=role.id,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                metadata={
                    "permissions_changed": permission_keys is not None,
                },
                allowlist=frozenset({"permissions_changed"}),
            )
            if permission_keys is not None:
                record_audit(
                    self.db,
                    action=AuditAction.ROLE_PERMISSIONS_CHANGED,
                    entity_type=AuditEntityType.ROLE,
                    entity_id=role.id,
                    workspace_id=workspace_id,
                    actor_user_id=actor_id,
                    metadata={"permission_keys": permission_keys},
                    allowlist=frozenset({"permission_keys"}),
                )
            self.db.commit()
            self.db.expire_all()
        except IntegrityError as exc:
            self.db.rollback()
            if "uq_workspace_roles_workspace_name" in str(exc).lower():
                raise AppError(
                    ErrorCategory.ROLE_NAME_TAKEN,
                    "A role with this name already exists in the workspace.",
                ) from exc
            raise
        loaded = self._get_role(workspace_id, role_id)
        return self._to_out(
            loaded, assigned=self._assignment_counts(workspace_id).get(loaded.id, 0)
        )

    def delete_role(
        self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.ROLES_MANAGE)
        role = self._get_role(workspace_id, role_id)
        if role.is_owner_role or role.is_system:
            raise AppError(
                ErrorCategory.ROLE_PROTECTED,
                "System roles cannot be deleted.",
            )
        assigned = self.memberships.count_for_role(role.id)
        pending = self._pending_invitation_count(workspace_id, role.id)
        if assigned > 0 or pending > 0:
            raise AppError(
                ErrorCategory.ROLE_IN_USE,
                "Reassign members (and pending invitations) before deleting this role.",
                details={"assigned_count": assigned, "pending_invitations": pending},
            )
        self.db.delete(role)
        record_audit(
            self.db,
            action=AuditAction.ROLE_DELETED,
            entity_type=AuditEntityType.ROLE,
            entity_id=role_id,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
        )
        self.db.commit()
        self.db.expire_all()

    def assignable_roles(
        self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID
    ) -> list[RoleOut]:
        """Roles that may be invited or assigned (excludes Owner)."""
        _, membership = self._workspace_svc.get_workspace_for_user(workspace_id, actor_id)
        require_permission(membership, WorkspacePermission.MEMBERS_VIEW)
        rows = list(
            self.db.scalars(
                select(WorkspaceRoleDef)
                .options(
                    selectinload(WorkspaceRoleDef.permission_links).selectinload(
                        WorkspaceRolePermission.permission
                    )
                )
                .where(
                    WorkspaceRoleDef.workspace_id == workspace_id,
                    WorkspaceRoleDef.is_owner_role.is_(False),
                )
                .order_by(WorkspaceRoleDef.created_at.asc())
            ).all()
        )
        counts = self._assignment_counts(workspace_id)
        return [self._to_out(row, assigned=counts.get(row.id, 0)) for row in rows]

    def _get_role(self, workspace_id: uuid.UUID, role_id: uuid.UUID) -> WorkspaceRoleDef:
        role = self.db.scalar(
            select(WorkspaceRoleDef)
            .options(
                selectinload(WorkspaceRoleDef.permission_links).selectinload(
                    WorkspaceRolePermission.permission
                )
            )
            .where(
                WorkspaceRoleDef.id == role_id,
                WorkspaceRoleDef.workspace_id == workspace_id,
            )
        )
        if role is None:
            raise AppError(ErrorCategory.ROLE_NOT_FOUND, "Role not found.")
        return role

    def _assignment_counts(self, workspace_id: uuid.UUID) -> dict[uuid.UUID, int]:
        rows = self.db.execute(
            select(WorkspaceMembership.role_id, func.count())
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .group_by(WorkspaceMembership.role_id)
        ).all()
        return {role_id: int(count) for role_id, count in rows}

    def _pending_invitation_count(self, workspace_id: uuid.UUID, role_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkspaceInvitation)
                .where(
                    WorkspaceInvitation.workspace_id == workspace_id,
                    WorkspaceInvitation.role_id == role_id,
                    WorkspaceInvitation.accepted_at.is_(None),
                    WorkspaceInvitation.revoked_at.is_(None),
                )
            )
            or 0
        )

    def _replace_permissions(self, role: WorkspaceRoleDef, keys: list[str]) -> None:
        desired = set(keys)
        current = {link.permission.key: link for link in list(role.permission_links)}
        for key, link in list(current.items()):
            if key not in desired:
                role.permission_links.remove(link)
        missing = desired - set(current)
        if not missing:
            return
        perms = {
            row.key: row
            for row in self.db.scalars(select(Permission).where(Permission.key.in_(missing))).all()
        }
        for key in missing:
            perm = perms.get(key)
            if perm is None:
                raise AppError(
                    ErrorCategory.UNKNOWN_PERMISSION,
                    "Unknown permission key.",
                    details={"permission": key},
                )
            role.permission_links.append(
                WorkspaceRolePermission(permission_id=perm.id, permission=perm)
            )

    @staticmethod
    def _validate_name(name: str) -> str:
        clean = " ".join((name or "").strip().split())
        if not clean:
            raise AppError(ErrorCategory.VALIDATION, "Role name is required.")
        if len(clean) > 100:
            raise AppError(ErrorCategory.VALIDATION, "Role name is too long.")
        return clean

    @staticmethod
    def _validate_assignable_keys(keys: list[str]) -> list[str]:
        seen: list[str] = []
        for raw in keys:
            parsed = parse_permission_key(raw)
            key = parsed.value
            if key in OWNER_ONLY_PERMISSION_KEYS:
                raise AppError(
                    ErrorCategory.ROLE_PROTECTED,
                    "This permission is reserved for the Workspace Owner.",
                    details={"permission": key},
                )
            if key not in ASSIGNABLE_PERMISSION_KEYS:
                raise AppError(
                    ErrorCategory.UNKNOWN_PERMISSION,
                    "Unknown permission key.",
                    details={"permission": key},
                )
            if key not in seen:
                seen.append(key)
        return seen

    @staticmethod
    def _to_out(role: WorkspaceRoleDef, *, assigned: int) -> RoleOut:
        if role.is_owner_role:
            from app.workspaces.permissions import ALL_PERMISSION_KEYS

            perms = sorted(ALL_PERMISSION_KEYS)
        else:
            perms = sorted(link.permission.key for link in role.permission_links)
        return RoleOut(
            id=role.id,
            workspace_id=role.workspace_id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            is_owner_role=role.is_owner_role,
            system_key=role.system_key,
            permissions=perms,
            assigned_count=assigned,
            created_at=role.created_at,
            updated_at=role.updated_at,
        )
