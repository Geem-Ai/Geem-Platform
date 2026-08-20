"""Platform Admin read models for Workspace / User inventory (Phase 12B)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api_keys.models import ApiKey
from app.apps_catalog.models import AppInstallation
from app.billing.models import Plan, Subscription, SubscriptionStatus
from app.documents.repository import ilike_contains_pattern
from app.experts.models import Expert, ExpertType
from app.identity.models import Session as AuthSession
from app.identity.models import User
from app.workspaces.models import (
    Workspace,
    WorkspaceKind,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceStatus,
)
from app.workspaces.repository import _MEMBERSHIP_ROLE_LOAD


class PlatformAdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Workspaces ---

    def count_workspaces(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        include_deleted: bool = False,
    ) -> int:
        stmt = select(func.count()).select_from(Workspace)
        stmt = self._apply_workspace_filters(
            stmt,
            search=search,
            status=status,
            kind=kind,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
        )
        return int(self.db.scalar(stmt) or 0)

    def list_workspaces(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        include_deleted: bool = False,
    ) -> list[Workspace]:
        stmt = select(Workspace)
        stmt = self._apply_workspace_filters(
            stmt,
            search=search,
            status=status,
            kind=kind,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
        )
        stmt = (
            stmt.order_by(Workspace.created_at.desc(), Workspace.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def get_workspace(self, workspace_id: uuid.UUID, *, include_deleted: bool = False) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        if not include_deleted:
            stmt = stmt.where(Workspace.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def member_counts(self, workspace_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not workspace_ids:
            return {}
        rows = self.db.execute(
            select(WorkspaceMembership.workspace_id, func.count())
            .where(WorkspaceMembership.workspace_id.in_(workspace_ids))
            .group_by(WorkspaceMembership.workspace_id)
        ).all()
        return {wid: int(count) for wid, count in rows}

    def expert_counts(self, workspace_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not workspace_ids:
            return {}
        rows = self.db.execute(
            select(Expert.workspace_id, func.count())
            .where(
                Expert.workspace_id.in_(workspace_ids),
                Expert.type == ExpertType.WORKSPACE.value,
                Expert.deleted_at.is_(None),
            )
            .group_by(Expert.workspace_id)
        ).all()
        return {wid: int(count) for wid, count in rows}

    def subscription_summaries(
        self, workspace_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Subscription, Plan]]:
        """Current active subscription + plan per workspace (read-only)."""
        if not workspace_ids:
            return {}
        rows = self.db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                Subscription.workspace_id.in_(workspace_ids),
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
        ).all()
        return {sub.workspace_id: (sub, plan) for sub, plan in rows}

    def list_members_page(
        self,
        workspace_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkspaceMembership], int]:
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .where(WorkspaceMembership.workspace_id == workspace_id)
            )
            or 0
        )
        rows = list(
            self.db.scalars(
                select(WorkspaceMembership)
                .options(
                    selectinload(WorkspaceMembership.user),
                    *_MEMBERSHIP_ROLE_LOAD,
                )
                .where(WorkspaceMembership.workspace_id == workspace_id)
                .order_by(WorkspaceMembership.created_at.asc(), WorkspaceMembership.id.asc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return rows, total

    def owner_memberships(self, workspace_id: uuid.UUID) -> list[WorkspaceMembership]:
        return list(
            self.db.scalars(
                select(WorkspaceMembership)
                .join(WorkspaceRoleDef, WorkspaceMembership.role_id == WorkspaceRoleDef.id)
                .options(
                    selectinload(WorkspaceMembership.user),
                    *_MEMBERSHIP_ROLE_LOAD,
                )
                .where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceRoleDef.is_owner_role.is_(True),
                )
                .order_by(WorkspaceMembership.created_at.asc())
            ).all()
        )

    def resource_counts(self, workspace_id: uuid.UUID) -> dict[str, int]:
        experts = int(
            self.db.scalar(
                select(func.count())
                .select_from(Expert)
                .where(
                    Expert.workspace_id == workspace_id,
                    Expert.type == ExpertType.WORKSPACE.value,
                    Expert.deleted_at.is_(None),
                )
            )
            or 0
        )
        api_keys = int(
            self.db.scalar(
                select(func.count())
                .select_from(ApiKey)
                .where(ApiKey.workspace_id == workspace_id, ApiKey.revoked_at.is_(None))
            )
            or 0
        )
        installations = int(
            self.db.scalar(
                select(func.count())
                .select_from(AppInstallation)
                .where(AppInstallation.workspace_id == workspace_id)
            )
            or 0
        )
        members = int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .where(WorkspaceMembership.workspace_id == workspace_id)
            )
            or 0
        )
        return {
            "members_count": members,
            "experts_count": experts,
            "api_keys_count": api_keys,
            "app_installations_count": installations,
        }

    @staticmethod
    def _apply_workspace_filters(
        stmt: Select[Any],
        *,
        search: str | None,
        status: str | None,
        kind: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
        include_deleted: bool,
    ) -> Select[Any]:
        if not include_deleted:
            stmt = stmt.where(Workspace.deleted_at.is_(None))
        if kind:
            stmt = stmt.where(Workspace.kind == kind)
        if status:
            stmt = stmt.where(Workspace.status == status)
        if created_from is not None:
            stmt = stmt.where(Workspace.created_at >= created_from)
        if created_to is not None:
            stmt = stmt.where(Workspace.created_at <= created_to)
        needle = (search or "").strip()
        if needle:
            pattern = ilike_contains_pattern(needle)
            stmt = stmt.where(
                or_(
                    Workspace.name.ilike(pattern, escape="\\"),
                    Workspace.slug.ilike(pattern, escape="\\"),
                )
            )
        return stmt

    # --- Users ---

    def count_users(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        platform_role: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        stmt = self._apply_user_filters(stmt, search=search, status=status, platform_role=platform_role)
        return int(self.db.scalar(stmt) or 0)

    def list_users(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        platform_role: str | None = None,
    ) -> list[User]:
        stmt = select(User).where(User.deleted_at.is_(None))
        stmt = self._apply_user_filters(stmt, search=search, status=status, platform_role=platform_role)
        stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def get_user(self, user_id: uuid.UUID) -> User | None:
        return self.db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))

    def membership_counts(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not user_ids:
            return {}
        rows = self.db.execute(
            select(WorkspaceMembership.user_id, func.count())
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(
                WorkspaceMembership.user_id.in_(user_ids),
                Workspace.deleted_at.is_(None),
                Workspace.kind == WorkspaceKind.TENANT.value,
                Workspace.status != WorkspaceStatus.ARCHIVED.value,
            )
            .group_by(WorkspaceMembership.user_id)
        ).all()
        return {uid: int(count) for uid, count in rows}

    def last_session_used_at(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime | None]:
        if not user_ids:
            return {}
        rows = self.db.execute(
            select(AuthSession.user_id, func.max(AuthSession.last_used_at))
            .where(AuthSession.user_id.in_(user_ids))
            .group_by(AuthSession.user_id)
        ).all()
        return {uid: used for uid, used in rows}

    def active_session_count(self, user_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > func.now(),
                )
            )
            or 0
        )

    def list_user_memberships(self, user_id: uuid.UUID) -> list[WorkspaceMembership]:
        return list(
            self.db.scalars(
                select(WorkspaceMembership)
                .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
                .options(
                    selectinload(WorkspaceMembership.workspace),
                    *_MEMBERSHIP_ROLE_LOAD,
                )
                .where(
                    WorkspaceMembership.user_id == user_id,
                    Workspace.deleted_at.is_(None),
                    Workspace.kind == WorkspaceKind.TENANT.value,
                )
                .order_by(WorkspaceMembership.created_at.desc(), WorkspaceMembership.id.desc())
            ).all()
        )

    @staticmethod
    def _apply_user_filters(
        stmt: Select[Any],
        *,
        search: str | None,
        status: str | None,
        platform_role: str | None,
    ) -> Select[Any]:
        if status:
            stmt = stmt.where(User.status == status)
        if platform_role:
            stmt = stmt.where(User.platform_role == platform_role)
        needle = (search or "").strip()
        if needle:
            pattern = ilike_contains_pattern(needle)
            stmt = stmt.where(User.email.ilike(pattern, escape="\\"))
        return stmt
