from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.workspaces.models import (
    Workspace,
    WorkspaceKind,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceRolePermission,
    WorkspaceStatus,
)


_MEMBERSHIP_ROLE_LOAD = (
    selectinload(WorkspaceMembership.workspace_role)
    .selectinload(WorkspaceRoleDef.permission_links)
    .selectinload(WorkspaceRolePermission.permission),
)


class WorkspaceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        return self.db.scalar(
            select(Workspace).where(
                Workspace.id == workspace_id,
                Workspace.deleted_at.is_(None),
            )
        )

    def get_by_slug(self, slug: str) -> Workspace | None:
        return self.db.scalar(
            select(Workspace).where(
                Workspace.slug == slug,
                Workspace.deleted_at.is_(None),
            )
        )

    def create(self, workspace: Workspace) -> Workspace:
        self.db.add(workspace)
        self.db.flush()
        return workspace

    def list_for_user(self, user_id: uuid.UUID) -> list[tuple[Workspace, WorkspaceMembership]]:
        """Tenant Workspaces only — system scopes never appear in switcher /auth/me."""
        rows = self.db.execute(
            select(Workspace, WorkspaceMembership)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .options(*_MEMBERSHIP_ROLE_LOAD)
            .where(
                WorkspaceMembership.user_id == user_id,
                Workspace.deleted_at.is_(None),
                Workspace.status != WorkspaceStatus.ARCHIVED.value,
                Workspace.kind == WorkspaceKind.TENANT.value,
            )
            .order_by(Workspace.created_at.asc())
        ).all()
        return [(w, m) for w, m in rows]


class MembershipRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceMembership | None:
        return self.db.scalar(
            select(WorkspaceMembership)
            .options(*_MEMBERSHIP_ROLE_LOAD)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )

    def get_for_update(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMembership | None:
        return self.db.scalar(
            select(WorkspaceMembership)
            .options(*_MEMBERSHIP_ROLE_LOAD)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
            .with_for_update()
        )

    def get_by_id(self, membership_id: uuid.UUID) -> WorkspaceMembership | None:
        return self.db.scalar(
            select(WorkspaceMembership)
            .options(*_MEMBERSHIP_ROLE_LOAD)
            .where(WorkspaceMembership.id == membership_id)
        )

    def create(self, membership: WorkspaceMembership) -> WorkspaceMembership:
        self.db.add(membership)
        self.db.flush()
        return membership

    def list_for_workspace(self, workspace_id: uuid.UUID) -> list[WorkspaceMembership]:
        return list(
            self.db.scalars(
                select(WorkspaceMembership)
                .options(
                    selectinload(WorkspaceMembership.user),
                    *_MEMBERSHIP_ROLE_LOAD,
                )
                .where(WorkspaceMembership.workspace_id == workspace_id)
                .order_by(WorkspaceMembership.created_at.asc())
            ).all()
        )

    def count_owners(self, workspace_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .join(WorkspaceRoleDef, WorkspaceMembership.role_id == WorkspaceRoleDef.id)
                .where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceRoleDef.is_owner_role.is_(True),
                )
            )
            or 0
        )

    def lock_owners(self, workspace_id: uuid.UUID) -> list[WorkspaceMembership]:
        """Lock owner rows (FOR UPDATE) before last-owner invariant checks."""
        return list(
            self.db.scalars(
                select(WorkspaceMembership)
                .join(WorkspaceRoleDef, WorkspaceMembership.role_id == WorkspaceRoleDef.id)
                .options(*_MEMBERSHIP_ROLE_LOAD)
                .where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceRoleDef.is_owner_role.is_(True),
                )
                .with_for_update()
            ).all()
        )

    def count_for_role(self, role_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .where(WorkspaceMembership.role_id == role_id)
            )
            or 0
        )

    def delete(self, membership: WorkspaceMembership) -> None:
        self.db.delete(membership)
        self.db.flush()
