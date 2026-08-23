"""App Store catalog, installations, and commercial access (Phase 9A/9B).

Connector/OAuth config payloads are encrypted but unused until 9C+.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
from app.workspaces.models import Workspace


class AppBillingType(str, enum.Enum):
    FREE = "free"
    ONE_TIME = "one_time"
    SUBSCRIPTION = "subscription"


class AppStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    COMING_SOON = "coming_soon"
    DISABLED = "disabled"


class AppPlanBillingInterval(str, enum.Enum):
    NONE = "none"
    MONTHLY = "monthly"


class AppInstallationStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    UNINSTALLED = "uninstalled"


class AppLicenseStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class AppSubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AppCommercialSource(str, enum.Enum):
    PURCHASE = "purchase"
    PLATFORM_ADMIN = "platform_admin"


class AppCategory(Base):
    __tablename__ = "app_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name_key: Mapped[str] = mapped_column(String(128), nullable=False)
    description_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    apps: Mapped[list[CatalogApp]] = relationship(back_populates="category")


class CatalogApp(Base):
    """Global App Store listing. Not a workspace installation."""

    __tablename__ = "apps"
    __table_args__ = (
        Index("ix_apps_category_id", "category_id"),
        Index("ix_apps_status_sort", "status", "sort_order"),
        Index("ix_apps_billing_type", "billing_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_description: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    icon_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    billing_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AppBillingType.FREE.value
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AppStatus.DRAFT.value, index=True
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Phase 9C — nullable until/unless the app is an external connector.
    connector_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    connector_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    config_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[AppCategory] = relationship(back_populates="apps")
    plans: Mapped[list[AppPlan]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )
    installations: Mapped[list[AppInstallation]] = relationship(back_populates="app")
    licenses: Mapped[list[AppLicense]] = relationship(back_populates="app")
    subscriptions: Mapped[list[AppSubscription]] = relationship(back_populates="app")


class AppPlan(Base):
    __tablename__ = "app_plans"
    __table_args__ = (
        UniqueConstraint("app_id", "code", name="uq_app_plans_app_code"),
        Index("ix_app_plans_app_id", "app_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_interval: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AppPlanBillingInterval.NONE.value
    )
    price_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="SAR", server_default="SAR"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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

    app: Mapped[CatalogApp] = relationship(back_populates="plans")
    entitlements: Mapped[list[AppPlanEntitlement]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class AppPlanEntitlement(Base):
    __tablename__ = "app_plan_entitlements"
    __table_args__ = (
        UniqueConstraint("app_plan_id", "key", name="uq_app_plan_entitlement_key"),
        Index("ix_app_plan_entitlements_plan_id", "app_plan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped[AppPlan] = relationship(back_populates="entitlements")


class AppInstallation(Base):
    """Tenant-owned installation. One logical row per (workspace, app)."""

    __tablename__ = "app_installations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "app_id", name="uq_app_installations_workspace_app"),
        Index("ix_app_installations_workspace_status", "workspace_id", "status"),
        Index("ix_app_installations_app_id", "app_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AppInstallationStatus.ACTIVE.value
    )
    installed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Encrypted JSON blob. Never expose via API DTOs.
    config_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship()
    app: Mapped[CatalogApp] = relationship(back_populates="installations")


class AppLicense(Base):
    """One-time commercial entitlement. Survives uninstall."""

    __tablename__ = "app_licenses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "app_id", name="uq_app_licenses_workspace_app"),
        Index("ix_app_licenses_workspace_app", "workspace_id", "app_id"),
        Index("ix_app_licenses_purchase_id", "purchase_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchases.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AppCommercialSource.PURCHASE.value,
        server_default="purchase",
    )
    grant_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AppLicenseStatus.ACTIVE.value
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship()
    app: Mapped[CatalogApp] = relationship(back_populates="licenses")
    plan: Mapped[AppPlan] = relationship()


class AppSubscription(Base):
    """Monthly App subscription. Access is time-aware, not status-only."""

    __tablename__ = "app_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "app_id", name="uq_app_subscriptions_workspace_app"
        ),
        Index("ix_app_subscriptions_workspace_status", "workspace_id", "status"),
        Index("ix_app_subscriptions_period_end", "current_period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("apps.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AppSubscriptionStatus.ACTIVE.value
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latest_purchase_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchases.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AppCommercialSource.PURCHASE.value,
        server_default="purchase",
    )
    grant_idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship()
    app: Mapped[CatalogApp] = relationship(back_populates="subscriptions")
    plan: Mapped[AppPlan] = relationship()
