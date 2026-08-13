"""Expert data access — scoped queries; never mix ownership populations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

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
