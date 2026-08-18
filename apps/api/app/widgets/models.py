"""Chat Widget instances (embeddable site widget)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WidgetInstanceStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WidgetInstance(Base):
    """One embeddable chat widget per workspace installation (v1 cap via entitlements)."""

    __tablename__ = "widget_instances"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "app_installation_id",
            name="uq_widget_instances_workspace_installation",
        ),
        Index("ix_widget_instances_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_installations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WidgetInstanceStatus.ACTIVE.value,
        server_default=WidgetInstanceStatus.ACTIVE.value,
    )
    expert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="Geem", server_default="Geem")
    subtitle: Mapped[str | None] = mapped_column(String(256), nullable=True)
    greeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ar", server_default="ar")
    position: Mapped[str] = mapped_column(
        String(32), nullable=False, default="bottom-right", server_default="bottom-right"
    )
    primary_color: Mapped[str] = mapped_column(
        String(16), nullable=False, default="#0e2f44", server_default="#0e2f44"
    )
    text_color: Mapped[str] = mapped_column(
        String(16), nullable=False, default="#f2f2f2", server_default="#f2f2f2"
    )
    # null or [] = allow any origin; non-empty = exact origin allowlist
    allowed_origins: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
