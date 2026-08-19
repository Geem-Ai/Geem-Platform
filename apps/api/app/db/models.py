from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
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

# Domain models registered on the same Base metadata (Phase 1A+).
from app.identity.models import (  # noqa: E402
    EmailVerificationToken,
    PasswordResetToken,
    Session,
    User,
)
from app.workspaces.models import (  # noqa: E402
    Permission,
    Workspace,
    WorkspaceInvitation,
    WorkspaceMembership,
    WorkspaceRoleDef,
    WorkspaceRolePermission,
)
from app.experts.models import (  # noqa: E402
    Expert,
    ExpertDocument,
    ExpertSource,
    WorkspaceExpertGrant,
)
from app.conversations.models import Conversation, Message  # noqa: E402
from app.chat_attachments.models import ChatAttachment  # noqa: E402
from app.billing.models import (  # noqa: E402
    CreditPack,
    PaymentGatewayConfig,
    Plan,
    PlanEntitlement,
    Purchase,
    Subscription,
)
from app.usage.models import (  # noqa: E402
    AiUsageReservation,
    CreditAccount,
    CreditLedgerEntry,
    StorageReservation,
    StorageUsageEvent,
    UsagePeriodCounter,
    WorkspaceResourceUsage,
)
from app.api_keys.models import ApiKey  # noqa: E402
from app.apps_catalog.models import (  # noqa: E402
    AppCategory,
    AppInstallation,
    AppLicense,
    AppPlan,
    AppPlanEntitlement,
    AppSubscription,
    CatalogApp,
)
from app.connectors.models import (  # noqa: E402
    AppConnection,
    ChannelBinding,
    ChannelConversationBinding,
    ConnectorItem,
    ConnectorSyncRun,
    ConnectorWebhookEvent,
)
from app.widgets.models import WidgetConversationBinding, WidgetInstance  # noqa: E402
from app.audit.models import AuditLog  # noqa: E402

__all__ = [
    "Document",
    "DocumentPage",
    "Chunk",
    "IngestionJob",
    "UsageEvent",
    "User",
    "Session",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceInvitation",
    "Permission",
    "WorkspaceRoleDef",
    "WorkspaceRolePermission",
    "Expert",
    "ExpertSource",
    "ExpertDocument",
    "WorkspaceExpertGrant",
    "Conversation",
    "Message",
    "ChatAttachment",
    "Plan",
    "PlanEntitlement",
    "Subscription",
    "PaymentGatewayConfig",
    "CreditPack",
    "Purchase",
    "CreditAccount",
    "CreditLedgerEntry",
    "UsagePeriodCounter",
    "StorageUsageEvent",
    "StorageReservation",
    "WorkspaceResourceUsage",
    "AiUsageReservation",
    "ApiKey",
    "AppCategory",
    "CatalogApp",
    "AppPlan",
    "AppPlanEntitlement",
    "AppInstallation",
    "AppLicense",
    "AppSubscription",
    "AppConnection",
    "ChannelBinding",
    "ChannelConversationBinding",
    "ConnectorSyncRun",
    "ConnectorItem",
    "ConnectorWebhookEvent",
    "WidgetInstance",
    "WidgetConversationBinding",
    "AuditLog",
]


class Document(Base, SoftDeleteMixin):
    """Document ownership (Phase 2C — Workspace required).

    - Every Document belongs to a Workspace (``workspace_id`` NOT NULL).
    - Hash uniqueness is workspace-scoped for active rows.
    - Soft-deleted rows (``deleted_at`` set) release the uniqueness slot.
    - FK uses RESTRICT (not CASCADE) so workspace hard-delete cannot silently
      wipe document history; workspace deletion/retention is a later phase.
    - Soft-delete keeps the row for audit/citations; Phase 8 Storage purge
      removes MinIO objects, Qdrant points, and derived chunks/pages.
    """

    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "uq_documents_workspace_sha256_active",
            "workspace_id",
            "sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_documents_workspace_created_at", "workspace_id", "created_at"),
        Index("ix_documents_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/pdf")
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    processing_version: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace] = relationship()
    pages: Mapped[list[DocumentPage]] = relationship(back_populates="document", cascade="all, delete-orphan")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan")
    jobs: Mapped[list[IngestionJob]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_page"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    raw_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arabic_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="pages")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="page", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_page_id",
            "ordinal",
            "embedding_version",
            name="uq_chunk_page_ordinal_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    qdrant_point_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(256), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")
    page: Mapped[DocumentPage] = relationship(back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="jobs")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index(
            "ix_usage_events_workspace_api_key_created",
            "workspace_id",
            "api_key_id",
            "created_at",
            postgresql_where=text("api_key_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "messages.id",
            ondelete="SET NULL",
            name="fk_usage_events_message_id",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
