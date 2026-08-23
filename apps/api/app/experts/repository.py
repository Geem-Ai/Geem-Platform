"""Expert data access — scoped queries; never mix ownership populations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.documents.repository import ilike_contains_pattern
from app.experts.models import (
    Expert,
    ExpertAvailabilityMode,
    ExpertDocument,
    ExpertSource,
    ExpertStatus,
    ExpertType,
    ExpertVisibility,
    WorkspaceExpertGrant,
)
from app.workspaces.models import Workspace


class ExpertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, expert_id: uuid.UUID, *, include_deleted: bool = False) -> Expert | None:
        stmt = select(Expert).where(Expert.id == expert_id)
        if not include_deleted:
            stmt = stmt.where(Expert.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def get_workspace_expert(
        self,
        workspace_id: uuid.UUID,
        expert_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> Expert | None:
        stmt = select(Expert).where(
            Expert.id == expert_id,
            Expert.type == ExpertType.WORKSPACE.value,
            Expert.workspace_id == workspace_id,
        )
        if not include_deleted:
            stmt = stmt.where(Expert.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def list_workspace_experts(self, workspace_id: uuid.UUID) -> list[Expert]:
        return list(
            self.db.scalars(
                select(Expert)
                .where(
                    Expert.type == ExpertType.WORKSPACE.value,
                    Expert.workspace_id == workspace_id,
                    Expert.deleted_at.is_(None),
                )
                .order_by(Expert.created_at.asc())
            )
        )

    def list_platform_experts(self, *, include_drafts: bool = True) -> list[Expert]:
        stmt = select(Expert).where(
            Expert.type == ExpertType.PLATFORM.value,
            Expert.deleted_at.is_(None),
        )
        if not include_drafts:
            stmt = stmt.where(Expert.visibility == ExpertVisibility.PLATFORM_PUBLISHED.value)
        return list(self.db.scalars(stmt.order_by(Expert.created_at.asc())))

    def _apply_platform_expert_filters(
        self,
        stmt,
        *,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        knowledge_mode: str | None = None,
        availability_mode: str | None = None,
        published: bool | None = None,
    ):
        stmt = stmt.where(
            Expert.type == ExpertType.PLATFORM.value,
            Expert.deleted_at.is_(None),
        )
        if search:
            pattern = ilike_contains_pattern(search.strip())
            stmt = stmt.where(
                or_(
                    Expert.name.ilike(pattern, escape="\\"),
                    Expert.description.ilike(pattern, escape="\\"),
                )
            )
        if status:
            stmt = stmt.where(Expert.status == status)
        if visibility:
            stmt = stmt.where(Expert.visibility == visibility)
        if knowledge_mode:
            stmt = stmt.where(Expert.knowledge_mode == knowledge_mode)
        if availability_mode:
            stmt = stmt.where(Expert.availability_mode == availability_mode)
        if published is True:
            stmt = stmt.where(Expert.visibility == ExpertVisibility.PLATFORM_PUBLISHED.value)
        elif published is False:
            stmt = stmt.where(Expert.visibility == ExpertVisibility.PLATFORM_DRAFT.value)
        return stmt

    def count_platform_experts(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        knowledge_mode: str | None = None,
        availability_mode: str | None = None,
        published: bool | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Expert)
        stmt = self._apply_platform_expert_filters(
            stmt,
            search=search,
            status=status,
            visibility=visibility,
            knowledge_mode=knowledge_mode,
            availability_mode=availability_mode,
            published=published,
        )
        return int(self.db.scalar(stmt) or 0)

    def list_platform_experts_paginated(
        self,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        status: str | None = None,
        visibility: str | None = None,
        knowledge_mode: str | None = None,
        availability_mode: str | None = None,
        published: bool | None = None,
    ) -> list[Expert]:
        stmt = select(Expert)
        stmt = self._apply_platform_expert_filters(
            stmt,
            search=search,
            status=status,
            visibility=visibility,
            knowledge_mode=knowledge_mode,
            availability_mode=availability_mode,
            published=published,
        )
        stmt = (
            stmt.order_by(Expert.created_at.desc(), Expert.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def count_grants_for_experts(self, expert_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not expert_ids:
            return {}
        rows = self.db.execute(
            select(WorkspaceExpertGrant.expert_id, func.count())
            .where(WorkspaceExpertGrant.expert_id.in_(expert_ids))
            .group_by(WorkspaceExpertGrant.expert_id)
        ).all()
        return {eid: int(count) for eid, count in rows}

    def count_document_links_for_experts(
        self, expert_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not expert_ids:
            return {}
        rows = self.db.execute(
            select(ExpertDocument.expert_id, func.count())
            .where(ExpertDocument.expert_id.in_(expert_ids))
            .group_by(ExpertDocument.expert_id)
        ).all()
        return {eid: int(count) for eid, count in rows}

    def list_available_platform_for_workspace(self, workspace_id: uuid.UUID) -> list[Expert]:
        """Published Platform Experts available to a tenant Workspace (grant or all_workspaces)."""
        granted = (
            select(WorkspaceExpertGrant.expert_id)
            .where(WorkspaceExpertGrant.workspace_id == workspace_id)
            .scalar_subquery()
        )
        return list(
            self.db.scalars(
                select(Expert)
                .where(
                    Expert.type == ExpertType.PLATFORM.value,
                    Expert.deleted_at.is_(None),
                    Expert.status != ExpertStatus.DISABLED.value,
                    Expert.visibility == ExpertVisibility.PLATFORM_PUBLISHED.value,
                    or_(
                        Expert.availability_mode == ExpertAvailabilityMode.ALL_WORKSPACES.value,
                        Expert.id.in_(granted),
                    ),
                )
                .order_by(Expert.created_at.asc())
            )
        )

    def create(self, expert: Expert) -> Expert:
        self.db.add(expert)
        self.db.flush()
        return expert

    def has_active_grant(self, workspace_id: uuid.UUID, expert_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(WorkspaceExpertGrant.id).where(
                    WorkspaceExpertGrant.workspace_id == workspace_id,
                    WorkspaceExpertGrant.expert_id == expert_id,
                )
            )
            is not None
        )

    def get_grant(
        self, workspace_id: uuid.UUID, expert_id: uuid.UUID
    ) -> WorkspaceExpertGrant | None:
        return self.db.scalar(
            select(WorkspaceExpertGrant).where(
                WorkspaceExpertGrant.workspace_id == workspace_id,
                WorkspaceExpertGrant.expert_id == expert_id,
            )
        )

    def create_grant(self, grant: WorkspaceExpertGrant) -> WorkspaceExpertGrant:
        self.db.add(grant)
        self.db.flush()
        return grant

    def delete_grant(self, grant: WorkspaceExpertGrant) -> None:
        self.db.delete(grant)
        self.db.flush()

    def list_grants_for_expert(self, expert_id: uuid.UUID) -> list[WorkspaceExpertGrant]:
        return list(
            self.db.scalars(
                select(WorkspaceExpertGrant)
                .where(WorkspaceExpertGrant.expert_id == expert_id)
                .order_by(WorkspaceExpertGrant.created_at.asc())
            )
        )

    def _workspace_grants_base(
        self, expert_id: uuid.UUID, *, search: str | None = None
    ):
        stmt = (
            select(WorkspaceExpertGrant, Workspace)
            .join(Workspace, Workspace.id == WorkspaceExpertGrant.workspace_id)
            .where(
                WorkspaceExpertGrant.expert_id == expert_id,
                Workspace.deleted_at.is_(None),
            )
        )
        if search and search.strip():
            pattern = ilike_contains_pattern(search.strip())
            stmt = stmt.where(
                or_(
                    Workspace.name.ilike(pattern, escape="\\"),
                    Workspace.slug.ilike(pattern, escape="\\"),
                )
            )
        return stmt

    def count_workspace_grants_for_expert(
        self, expert_id: uuid.UUID, *, search: str | None = None
    ) -> int:
        stmt = select(func.count()).select_from(WorkspaceExpertGrant).join(
            Workspace, Workspace.id == WorkspaceExpertGrant.workspace_id
        ).where(
            WorkspaceExpertGrant.expert_id == expert_id,
            Workspace.deleted_at.is_(None),
        )
        if search and search.strip():
            pattern = ilike_contains_pattern(search.strip())
            stmt = stmt.where(
                or_(
                    Workspace.name.ilike(pattern, escape="\\"),
                    Workspace.slug.ilike(pattern, escape="\\"),
                )
            )
        return int(self.db.scalar(stmt) or 0)

    def list_workspace_grants_for_expert(
        self,
        expert_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
    ) -> list[tuple[WorkspaceExpertGrant, Workspace]]:
        stmt = self._workspace_grants_base(expert_id, search=search).order_by(
            WorkspaceExpertGrant.created_at.desc(),
            WorkspaceExpertGrant.id.desc(),
        )
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).all())

    def get_document_link(
        self, expert_id: uuid.UUID, document_id: uuid.UUID
    ) -> ExpertDocument | None:
        return self.db.scalar(
            select(ExpertDocument).where(
                ExpertDocument.expert_id == expert_id,
                ExpertDocument.document_id == document_id,
            )
        )

    def list_document_links(self, expert_id: uuid.UUID) -> list[ExpertDocument]:
        return list(
            self.db.scalars(
                select(ExpertDocument)
                .where(ExpertDocument.expert_id == expert_id)
                .order_by(ExpertDocument.created_at.asc())
            )
        )

    def count_document_links(self, expert_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(ExpertDocument)
                .where(ExpertDocument.expert_id == expert_id)
            )
            or 0
        )

    def create_document_link(self, link: ExpertDocument) -> ExpertDocument:
        self.db.add(link)
        self.db.flush()
        return link

    def delete_document_link(self, link: ExpertDocument) -> None:
        self.db.delete(link)
        self.db.flush()

    def create_source(self, source: ExpertSource) -> ExpertSource:
        self.db.add(source)
        self.db.flush()
        return source

    def get_source(self, expert_id: uuid.UUID, source_id: uuid.UUID) -> ExpertSource | None:
        return self.db.scalar(
            select(ExpertSource).where(
                ExpertSource.id == source_id,
                ExpertSource.expert_id == expert_id,
                ExpertSource.deleted_at.is_(None),
            )
        )

    def list_sources(self, expert_id: uuid.UUID) -> list[ExpertSource]:
        return list(
            self.db.scalars(
                select(ExpertSource)
                .where(
                    ExpertSource.expert_id == expert_id,
                    ExpertSource.deleted_at.is_(None),
                )
                .order_by(ExpertSource.created_at.asc())
            )
        )
