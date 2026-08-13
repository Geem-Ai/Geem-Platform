"""Credit accounts, ledger, period counters, storage events, AI reservations.

Ledger rows are append-only for type/amount/history. ``remaining_amount`` on
GRANT rows is the FIFO allocation cursor (Phase 5B) — not a rewrite of the
original grant.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.usage.metrics import (
    AiUsageReservationStatus,
    CreditLedgerEntryType,
    StorageReservationStatus,
    StorageUsageReason,
    UsageMetric,
)
from app.usage.periods import PeriodType


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_credit_accounts_balance_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ledger_entries: Mapped[list[CreditLedgerEntry]] = relationship(back_populates="account")


class CreditLedgerEntry(Base):
    """Credit movement. Type/amount/history are append-only.

    ``remaining_amount`` on GRANT rows is the FIFO allocation cursor and is
    updated in place by ``AiUsageService`` (not a rewrite of the grant).
    """

    __tablename__ = "credit_ledger_entries"
    __table_args__ = (
        Index(
            "uq_credit_ledger_workspace_request_id",
            "workspace_id",
            "request_id",
            unique=True,
            postgresql_where=text("request_id IS NOT NULL"),
        ),
        Index("ix_credit_ledger_workspace_created", "workspace_id", "created_at"),
        Index("ix_credit_ledger_account_id", "credit_account_id"),
        CheckConstraint(
            "remaining_amount IS NULL OR remaining_amount >= 0",
            name="ck_credit_ledger_remaining_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    credit_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entry_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CreditLedgerEntryType.GRANT.value
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[CreditAccount] = relationship(back_populates="ledger_entries")


class UsagePeriodCounter(Base):
    """Per-workspace period meters. Concurrent increment is Phase 5B."""

    __tablename__ = "usage_period_counters"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "metric",
            "period_type",
            "period_start",
            name="uq_usage_period_counter",
        ),
        Index("ix_usage_period_counters_workspace", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(String(64), nullable=False, default=UsageMetric.AI_TOKENS.value)
    period_type: Mapped[str] = mapped_column(String(32), nullable=False, default=PeriodType.DAILY.value)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StorageUsageEvent(Base):
    """Append-only audit of storage byte changes."""

    __tablename__ = "storage_usage_events"
    __table_args__ = (Index("ix_storage_usage_events_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    delta_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StorageUsageReason.UPLOAD.value
    )
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceResourceUsage(Base):
    """In-flight reserved bytes for one Workspace metric (Phase 5C).

    Billable storage *used* is the live SUM of active Document.byte_size.
    This row only tracks ``reserved_bytes`` so concurrent uploads cannot
    overshoot the entitlement while a blob is being persisted.
    """

    __tablename__ = "workspace_resource_usage"
    __table_args__ = (
        UniqueConstraint("workspace_id", "metric", name="uq_workspace_resource_usage"),
        CheckConstraint("reserved_bytes >= 0", name="ck_workspace_resource_usage_reserved_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric: Mapped[str] = mapped_column(
        String(64), nullable=False, default=UsageMetric.STORAGE_BYTES.value
    )
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StorageReservation(Base):
    """Durable hold for one chargeable Workspace blob (request_id idempotency)."""

    __tablename__ = "storage_reservations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "request_id",
            name="uq_storage_reservations_workspace_request",
        ),
        Index("ix_storage_reservations_workspace", "workspace_id"),
        CheckConstraint(
            "status IN ('reserved', 'finalized', 'released')",
            name="ck_storage_reservations_status",
        ),
        CheckConstraint("byte_size >= 0", name="ck_storage_reservations_byte_size_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=StorageReservationStatus.RESERVED.value
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AiUsageReservation(Base):
    """Durable hold for one billable AI generation (``request_id`` idempotency)."""

    __tablename__ = "ai_usage_reservations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "request_id",
            name="uq_ai_usage_reservations_workspace_request",
        ),
        Index("ix_ai_usage_reservations_workspace", "workspace_id"),
        CheckConstraint(
            "status IN ('reserved', 'settled', 'released')",
            name="ck_ai_usage_reservations_status",
        ),
        CheckConstraint(
            "estimated_tokens >= 0",
            name="ck_ai_usage_reservations_estimated_non_negative",
        ),
        CheckConstraint(
            "included_reserved >= 0",
            name="ck_ai_usage_reservations_included_reserved_non_negative",
        ),
        CheckConstraint(
            "credit_reserved >= 0",
            name="ck_ai_usage_reservations_credit_reserved_non_negative",
        ),
        CheckConstraint(
            "included_settled >= 0",
            name="ck_ai_usage_reservations_included_settled_non_negative",
        ),
        CheckConstraint(
            "credit_settled >= 0",
            name="ck_ai_usage_reservations_credit_settled_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AiUsageReservationStatus.RESERVED.value
    )
    estimated_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    included_reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    actual_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    included_settled: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_settled: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_allocations: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    daily_counter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usage_period_counters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weekly_counter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usage_period_counters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    monthly_counter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usage_period_counters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expert_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
