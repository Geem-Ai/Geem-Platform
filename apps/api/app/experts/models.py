"""Expert domain models (Phases 3A + 3B).

Status vs visibility
--------------------
* ``status`` — Expert availability/lifecycle (not raw Document ingestion state).

  Phase 3B derives ``status`` from linked Document ingestion state via
  ``ExpertStatusReconciler`` (unless the Expert is DISABLED, which is manual):

  - ``draft``: no linked knowledge / nothing ready yet
  - ``processing``: at least one linked Document is queued / processing (and no
    ready Documents to serve yet)
  - ``ready``: at least one linked Document is ``ready`` (some may still be
    processing / failed)
  - ``failed``: all linked Documents are ``failed`` (no ``ready`` docs left)
  - ``disabled``: intentionally unavailable — sticky; never auto-overwritten

* ``visibility`` — who may discover the Expert once status allows:
  - Workspace Experts: ``private`` | ``workspace``
  - Platform Experts: ``platform_draft`` | ``platform_published``

Platform Expert availability further requires an explicit Workspace grant
(unless ``availability_mode=all_workspaces``) — never inferred from visibility
alone.

Document ownership remains Workspace-scoped (``documents.workspace_id`` NOT
NULL). Platform Expert Documents live under the internal Platform Knowledge
system Workspace; retrieval still filters by that Workspace (never global).

``ExpertSource.status`` (Phase 3B)
----------------------------------
Aligned with the linked-Document ingestion lifecycle used by
ExpertStatusReconciler. ``ACTIVE`` is kept as a compat alias of ``READY`` for
Phase 3A callers / stored rows that predate 3B.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.soft_delete import SoftDeleteMixin
from app.db.session import Base


class ExpertType(str, enum.Enum):
    WORKSPACE = "workspace"
    PLATFORM = "platform"


class ExpertStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    DISABLED = "disabled"
    PROCESSING = "processing"
    FAILED = "failed"


class ExpertVisibility(str, enum.Enum):
    PRIVATE = "private"
    WORKSPACE = "workspace"
    PLATFORM_DRAFT = "platform_draft"
    PLATFORM_PUBLISHED = "platform_published"


class ExpertAvailabilityMode(str, enum.Enum):
    """How a published Platform Expert is offered to Workspaces."""

    SELECTED_WORKSPACES = "selected_workspaces"
    ALL_WORKSPACES = "all_workspaces"


class ExpertSourceType(str, enum.Enum):
    UPLOAD = "upload"


class ExpertSourceStatus(str, enum.Enum):
    """ExpertSource lifecycle (Phase 3B).

    ``ACTIVE`` is kept as a compat alias of ``READY`` — code paths that stored
    "active" pre-3B continue to load without a migration; new writes should
    prefer ``READY`` / ``PROCESSING`` / ``FAILED`` / ``PENDING``.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DISABLED = "disabled"
    ACTIVE = "active"  # compat alias of READY (Phase 3A rows)


# Sensible defaults for stored rag_config; Phase 3B applies them at retrieval.
DEFAULT_RAG_CONFIG: dict[str, Any] = {}
SUPPORTED_RAG_CONFIG_KEYS = frozenset({"top_k", "rerank_top_n", "similarity_threshold"})

MAX_SYSTEM_INSTRUCTIONS_LENGTH = 32_000
MAX_EXPERT_NAME_LENGTH = 200
MAX_EXPERT_DESCRIPTION_LENGTH = 2_000


class Expert(Base, SoftDeleteMixin):
    __tablename__ = "experts"
    __table_args__ = (
        CheckConstraint(
            "(type = 'workspace' AND workspace_id IS NOT NULL) OR "
            "(type = 'platform' AND workspace_id IS NULL)",
            name="ck_experts_type_workspace_ownership",
        ),
        Index("ix_experts_workspace_id", "workspace_id"),
        Index("ix_experts_type", "type"),
        Index("ix_experts_status", "status"),
        Index("ix_experts_visibility", "visibility"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(MAX_EXPERT_NAME_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    icon_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rag_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExpertStatus.DRAFT.value
    )
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExpertVisibility.WORKSPACE.value
    )
    availability_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExpertAvailabilityMode.SELECTED_WORKSPACES.value,
        server_default=ExpertAvailabilityMode.SELECTED_WORKSPACES.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list[ExpertSource]] = relationship(
        back_populates="expert", cascade="all, delete-orphan"
    )
    document_links: Mapped[list[ExpertDocument]] = relationship(
        back_populates="expert", cascade="all, delete-orphan"
    )
    grants: Mapped[list[WorkspaceExpertGrant]] = relationship(
        back_populates="expert", cascade="all, delete-orphan"
    )

    @property
    def is_workspace_expert(self) -> bool:
        return self.type == ExpertType.WORKSPACE.value

    @property
    def is_platform_expert(self) -> bool:
        return self.type == ExpertType.PLATFORM.value


class ExpertSource(Base, SoftDeleteMixin):
    __tablename__ = "expert_sources"
    __table_args__ = (Index("ix_expert_sources_expert_id", "expert_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experts.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExpertSourceType.UPLOAD.value
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ExpertSourceStatus.ACTIVE.value
    )
    # Non-secret connector metadata only — never store credentials here.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    expert: Mapped[Expert] = relationship(back_populates="sources")
    documents: Mapped[list[ExpertDocument]] = relationship(back_populates="source")


class ExpertDocument(Base):
    """Many-to-many membership: one Document may belong to multiple Experts in-scope."""

    __tablename__ = "expert_documents"
    __table_args__ = (
        UniqueConstraint("expert_id", "document_id", name="uq_expert_document"),
        Index("ix_expert_documents_expert_id", "expert_id"),
        Index("ix_expert_documents_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experts.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expert_sources.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    expert: Mapped[Expert] = relationship(back_populates="document_links")
    source: Mapped[ExpertSource | None] = relationship(back_populates="documents")


class WorkspaceExpertGrant(Base):
    """Grants a published Platform Expert to a tenant Workspace."""

    __tablename__ = "workspace_expert_grants"
    __table_args__ = (
        UniqueConstraint("workspace_id", "expert_id", name="uq_workspace_expert_grant"),
        Index("ix_workspace_expert_grants_workspace_id", "workspace_id"),
        Index("ix_workspace_expert_grants_expert_id", "expert_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experts.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    expert: Mapped[Expert] = relationship(back_populates="grants")
