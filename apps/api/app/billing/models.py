"""Plans, subscriptions, payment gateways, credit packs, and purchases.

Phase 5A: plans / entitlements / subscriptions.
Phase 6A: payment_gateway_configs, credit_packs, purchases.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    EXPIRED = "expired"


class Plan(Base):
    """Catalog plan. Business limits live on PlanEntitlement rows, never plan code."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PlanStatus.ACTIVE.value, index=True
    )
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="SAR", server_default="SAR"
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

    entitlements: Mapped[list[PlanEntitlement]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="plan")

    @property
    def is_active(self) -> bool:
        return self.status == PlanStatus.ACTIVE.value


class PlanEntitlement(Base):
    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "key", name="uq_plan_entitlement_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False, default="integer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped[Plan] = relationship(back_populates="entitlements")


class Subscription(Base):
    """Workspace subscription. At most one ``active`` row per Workspace."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index(
            "uq_subscriptions_workspace_active",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_subscriptions_workspace_status", "workspace_id", "status"),
        Index("ix_subscriptions_plan_id", "plan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SubscriptionStatus.ACTIVE.value, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    plan: Mapped[Plan] = relationship(back_populates="subscriptions")


class PaymentGatewayCode(str, enum.Enum):
    CLICKPAY = "clickpay"
    NOOP = "noop"


class PurchaseKind(str, enum.Enum):
    SUBSCRIPTION = "subscription"
    CREDIT_PACK = "credit_pack"


class PurchaseStatus(str, enum.Enum):
    PENDING = "pending"
    REDIRECTED = "redirected"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentGatewayConfig(Base):
    """Configured payment adapters. At most one row may be enabled."""

    __tablename__ = "payment_gateway_configs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_payment_gateway_configs_code"),
        Index(
            "uq_payment_gateway_configs_one_enabled",
            "enabled",
            unique=True,
            postgresql_where=text("enabled = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
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

    purchases: Mapped[list[Purchase]] = relationship(back_populates="gateway_config")


class CreditPack(Base):
    """Catalog item that grants purchased AI credits after verified payment."""

    __tablename__ = "credit_packs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_credit_packs_code"),
        CheckConstraint("credits > 0", name="ck_credit_packs_credits_positive"),
        CheckConstraint("price_amount > 0", name="ck_credit_packs_price_positive"),
        Index("ix_credit_packs_active", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="SAR", server_default="SAR"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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


class Purchase(Base):
    """Workspace checkout attempt. Fulfillment uses ``payload``, never client input."""

    __tablename__ = "purchases"
    __table_args__ = (
        UniqueConstraint("cart_id", name="uq_purchases_cart_id"),
        UniqueConstraint("return_token_hash", name="uq_purchases_return_token_hash"),
        Index(
            "uq_purchases_provider_transaction_ref",
            "provider_transaction_ref",
            unique=True,
            postgresql_where=text("provider_transaction_ref IS NOT NULL"),
        ),
        Index("ix_purchases_workspace_created", "workspace_id", "created_at"),
        Index("ix_purchases_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "kind IN ('subscription', 'credit_pack')",
            name="ck_purchases_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'redirected', 'paid', 'failed', 'cancelled', 'expired')",
            name="ck_purchases_status",
        ),
        CheckConstraint("amount > 0", name="ck_purchases_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PurchaseStatus.PENDING.value, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="SAR", server_default="SAR"
    )
    payment_gateway_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_gateway_configs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cart_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_transaction_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    gateway_config: Mapped[PaymentGatewayConfig] = relationship(back_populates="purchases")
