from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.security_log import security_log
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import (
    Workspace,
    WorkspaceKind,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceStatus,
)
from app.workspaces.permissions import SystemRoleKey, WorkspacePermission
from app.workspaces.policy import WorkspaceAction, WorkspacePolicy
from app.workspaces.rbac_seed import ensure_default_workspace_roles, seed_permission_catalog
from app.workspaces.rbac_service import is_owner_membership, require_permission
from app.workspaces.repository import MembershipRepository, WorkspaceRepository
from app.workspaces.slug import validate_workspace_slug


def _is_slug_unique_violation(exc: IntegrityError) -> bool:
    """True only for the active-slug unique index, not plan/subscription uniques."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint = (getattr(diag, "constraint_name", None) or "") if diag is not None else ""
    if "slug" in constraint.lower():
        return True
    blob = str(orig or exc).lower()
    return "uq_workspaces_slug" in blob or "workspaces_slug" in blob


class WorkspaceService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.workspaces = WorkspaceRepository(db)
        self.memberships = MembershipRepository(db)

    def create_workspace(
        self,
        *,
        name: str,
        slug: str,
        created_by: uuid.UUID,
        settings: dict[str, Any] | None = None,
    ) -> tuple[Workspace, WorkspaceMembership]:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 200:
            raise AppError(ErrorCategory.VALIDATION, "Workspace name is required (max 200 chars).")
        clean_slug = validate_workspace_slug(slug, settings=self.settings)

        if self.workspaces.get_by_slug(clean_slug) is not None:
            raise AppError(ErrorCategory.WORKSPACE_SLUG_TAKEN, "Workspace slug is already taken.")

        workspace = Workspace(
            name=clean_name,
            slug=clean_slug,
            kind=WorkspaceKind.TENANT.value,
            status=WorkspaceStatus.ACTIVE.value,
            created_by=created_by,
            settings=settings or {},
        )
        try:
            # Single commit: workspace + default roles + owner membership + billing.
            self.workspaces.create(workspace)
            seed_permission_catalog(self.db)
            roles = ensure_default_workspace_roles(self.db, workspace.id)
            membership = WorkspaceMembership(
                workspace=workspace,
                user_id=created_by,
                role_id=roles[SystemRoleKey.OWNER.value].id,
            )
            self.memberships.create(membership)
            self._provision_tenant_billing(workspace)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _is_slug_unique_violation(exc):
                raise AppError(
                    ErrorCategory.WORKSPACE_SLUG_TAKEN,
                    "Workspace slug is already taken.",
                ) from exc
            raise
        except Exception:
            self.db.rollback()
            raise

        security_log(
            "workspace.created",
            workspace_id=str(workspace.id),
            slug=workspace.slug,
            user_id=str(created_by),
        )
        return workspace, membership

    def list_for_user(self, user_id: uuid.UUID) -> list[tuple[Workspace, WorkspaceMembership]]:
        return self.workspaces.list_for_user(user_id)

    def _reject_system_workspace(self, workspace: Workspace, *, user_id: uuid.UUID) -> None:
        """System Workspaces are never selectable as tenant current Workspace."""
        if workspace.kind == WorkspaceKind.SYSTEM.value:
            security_log(
                "workspace.system_access_denied",
                workspace_id=str(workspace.id),
                user_id=str(user_id),
                slug=workspace.slug,
            )
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")

    def get_workspace_for_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Workspace, WorkspaceMembership]:
        workspace = self.workspaces.get_by_id(workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        self._reject_system_workspace(workspace, user_id=user_id)
        membership = self.memberships.get(workspace_id, user_id)
        if membership is None:
            security_log(
                "workspace.access_denied",
                workspace_id=str(workspace_id),
                user_id=str(user_id),
            )
            raise AppError(ErrorCategory.WORKSPACE_ACCESS_DENIED, "Not a member of this workspace.")
        return workspace, membership

    def get_by_slug_for_user(
        self, slug: str, user_id: uuid.UUID
    ) -> tuple[Workspace, WorkspaceMembership]:
        workspace = self.workspaces.get_by_slug(slug)
        if workspace is None:
            raise AppError(ErrorCategory.WORKSPACE_NOT_FOUND, "Workspace not found.")
        self._reject_system_workspace(workspace, user_id=user_id)
        return self.get_workspace_for_user(workspace.id, user_id)

    def update_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        name: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> Workspace:
        workspace, membership = self.get_workspace_for_user(workspace_id, actor_id)
        WorkspacePolicy.require(membership, WorkspaceAction.UPDATE_WORKSPACE)
        if name is not None:
            clean = name.strip()
            if not clean or len(clean) > 200:
                raise AppError(ErrorCategory.VALIDATION, "Invalid workspace name.")
            workspace.name = clean
        if settings is not None:
            workspace.settings = settings
        self.db.commit()
        security_log(
            "workspace.updated",
            workspace_id=str(workspace.id),
            user_id=str(actor_id),
        )
        return workspace

    def list_members(
        self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID
    ) -> list[WorkspaceMembership]:
        _, membership = self.get_workspace_for_user(workspace_id, actor_id)
        WorkspacePolicy.require(membership, WorkspaceAction.VIEW_MEMBERS)
        return self.memberships.list_for_workspace(workspace_id)

    def _role_in_workspace(
        self, workspace_id: uuid.UUID, role_id: uuid.UUID
    ) -> WorkspaceRoleDef:
        role = self.db.get(WorkspaceRoleDef, role_id)
        if role is None or role.workspace_id != workspace_id:
            raise AppError(ErrorCategory.ROLE_NOT_FOUND, "Role not found.")
        return role

    def update_member_role(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
        new_role_id: uuid.UUID,
    ) -> WorkspaceMembership:
        _, actor_membership = self.get_workspace_for_user(workspace_id, actor_id)
        require_permission(actor_membership, WorkspacePermission.MEMBERS_UPDATE_ROLE)

        new_role = self._role_in_workspace(workspace_id, new_role_id)
        actor_is_owner = is_owner_membership(actor_membership)

        if new_role.is_owner_role:
            if not actor_is_owner:
                raise AppError(
                    ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                    "Only the workspace owner can assign the Owner role.",
                )
            require_permission(actor_membership, WorkspacePermission.MEMBERS_PROMOTE_OWNER)

        target = self.memberships.get_for_update(workspace_id, target_user_id)
        if target is None:
            raise AppError(ErrorCategory.MEMBERSHIP_NOT_FOUND, "Membership not found.")

        target_is_owner = is_owner_membership(target)
        if target_is_owner and not actor_is_owner:
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                "Only the workspace owner can modify owner memberships.",
            )

        owners = self.memberships.lock_owners(workspace_id)
        if target_is_owner and not new_role.is_owner_role and len(owners) <= 1:
            raise AppError(
                ErrorCategory.LAST_WORKSPACE_OWNER,
                "Cannot demote the last workspace owner.",
            )

        target.role_id = new_role.id
        target.workspace_role = new_role
        self.db.commit()
        self.db.refresh(target)
        security_log(
            "workspace.membership_role_changed",
            workspace_id=str(workspace_id),
            actor_id=str(actor_id),
            target_user_id=str(target_user_id),
            role_id=str(new_role.id),
            system_key=new_role.system_key,
        )
        return target

    def remove_member(
        self,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        _, actor_membership = self.get_workspace_for_user(workspace_id, actor_id)
        require_permission(actor_membership, WorkspacePermission.MEMBERS_REMOVE)

        target = self.memberships.get_for_update(workspace_id, target_user_id)
        if target is None:
            raise AppError(ErrorCategory.MEMBERSHIP_NOT_FOUND, "Membership not found.")

        actor_is_owner = is_owner_membership(actor_membership)
        target_is_owner = is_owner_membership(target)
        if target_is_owner and not actor_is_owner:
            raise AppError(
                ErrorCategory.INSUFFICIENT_WORKSPACE_ROLE,
                "Only the workspace owner can remove owners.",
            )

        owners = self.memberships.lock_owners(workspace_id)
        if target_is_owner and len(owners) <= 1:
            raise AppError(
                ErrorCategory.LAST_WORKSPACE_OWNER,
                "Cannot remove the last workspace owner.",
            )

        self.memberships.delete(target)
        self.db.commit()
        security_log(
            "workspace.membership_removed",
            workspace_id=str(workspace_id),
            actor_id=str(actor_id),
            target_user_id=str(target_user_id),
        )

    def ensure_migration_workspace(self, *, created_by: uuid.UUID | None = None) -> Workspace:
        """Create or resolve the default migration workspace (Phase 2 attaches documents)."""
        slug = validate_workspace_slug(self.settings.default_workspace_slug, settings=self.settings)
        existing = self.workspaces.get_by_slug(slug)
        if existing is not None:
            if existing.kind != WorkspaceKind.TENANT.value:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Default workspace slug collides with a system Workspace.",
                )
            if created_by is not None and self.memberships.get(existing.id, created_by) is None:
                seed_permission_catalog(self.db)
                roles = ensure_default_workspace_roles(self.db, existing.id)
                self.memberships.create(
                    WorkspaceMembership(
                        workspace_id=existing.id,
                        user_id=created_by,
                        role_id=roles[SystemRoleKey.OWNER.value].id,
                    )
                )
                if existing.created_by is None:
                    existing.created_by = created_by
                security_log(
                    "workspace.migration_owner_attached",
                    workspace_id=str(existing.id),
                    slug=slug,
                    actor_id=str(created_by),
                )
            self._provision_tenant_billing(existing)
            seed_permission_catalog(self.db)
            ensure_default_workspace_roles(self.db, existing.id)
            self.db.commit()
            return existing

        workspace = Workspace(
            name=self.settings.default_workspace_name,
            slug=slug,
            kind=WorkspaceKind.TENANT.value,
            status=WorkspaceStatus.ACTIVE.value,
            created_by=created_by,
            settings={"migration": True},
        )
        self.workspaces.create(workspace)
        seed_permission_catalog(self.db)
        roles = ensure_default_workspace_roles(self.db, workspace.id)
        if created_by is not None:
            self.memberships.create(
                WorkspaceMembership(
                    workspace_id=workspace.id,
                    user_id=created_by,
                    role_id=roles[SystemRoleKey.OWNER.value].id,
                )
            )
        self._provision_tenant_billing(workspace)
        self.db.commit()
        security_log("workspace.migration_bootstrap", workspace_id=str(workspace.id), slug=slug)
        return workspace

    def ensure_platform_knowledge_workspace(self) -> Workspace:
        """Idempotent bootstrap of the internal Platform Knowledge system Workspace.

        - kind=system — never listed for tenants, never selectable via hostname/membership
        - No ordinary memberships (platform_role=admin uses privileged services)
        - Slug is reserved from tenant registration
        """
        slug = self.settings.platform_knowledge_workspace_slug.strip().lower()
        if not slug:
            raise AppError(ErrorCategory.VALIDATION, "PLATFORM_KNOWLEDGE_WORKSPACE_SLUG is required.")

        existing = self.workspaces.get_by_slug(slug)
        if existing is not None:
            if existing.kind != WorkspaceKind.SYSTEM.value:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Platform knowledge slug is already used by a non-system Workspace.",
                    details={"slug": slug},
                )
            return existing

        # Bypass validate_workspace_slug reserved check — this slug is intentionally reserved.
        from app.workspaces.slug import _SLUG_RE, normalize_slug

        clean = normalize_slug(slug)
        if not _SLUG_RE.match(clean):
            raise AppError(
                ErrorCategory.WORKSPACE_SLUG_INVALID,
                "Platform knowledge workspace slug is invalid.",
                details={"slug": clean},
            )

        workspace = Workspace(
            name=self.settings.platform_knowledge_workspace_name,
            slug=clean,
            kind=WorkspaceKind.SYSTEM.value,
            status=WorkspaceStatus.ACTIVE.value,
            created_by=None,
            settings={"platform_knowledge": True},
        )
        self.workspaces.create(workspace)
        self.db.commit()
        security_log(
            "workspace.platform_knowledge_bootstrap",
            workspace_id=str(workspace.id),
            slug=clean,
            kind=WorkspaceKind.SYSTEM.value,
        )
        return workspace

    def get_platform_knowledge_workspace(self) -> Workspace:
        """Resolve the Platform Knowledge Workspace; create if missing."""
        return self.ensure_platform_knowledge_workspace()

    def _provision_tenant_billing(self, workspace: Workspace) -> None:
        """Attach bootstrap subscription + credit account. Caller owns commit."""
        if workspace.kind != WorkspaceKind.TENANT.value:
            return
        from app.billing.provisioning import provision_tenant_workspace

        provision_tenant_workspace(self.db, workspace.id, settings=self.settings)
