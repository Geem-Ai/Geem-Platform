"""Conversation + Message domain models (Phase 4A / 9F channel).

Hierarchy
---------
Workspace (consumer tenant)
  └── User (workspace Chat) *or* channel binding (WhatsApp)
       └── Conversation
            ├── Expert (Workspace Expert *or* granted Platform Expert)
            └── Messages

``conversation.workspace_id`` is always the **consumer** Workspace. For Platform
Experts this is *not* equal to the Expert's knowledge Workspace (Platform
Knowledge system Workspace). Never assume ``conversation.workspace_id ==
expert.workspace_id``.

Workspace Chat conversations are private to ``user_id`` within the consumer
Workspace. Channel conversations use ``source=channel`` with ``user_id`` null and
must not appear in personal Chat history listings. Widget conversations use
``source=widget`` with ``user_id`` null (keyed by visitor ``session_id``).
"""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.soft_delete import SoftDeleteMixin
from app.db.session import Base


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(str, enum.Enum):
    """Message lifecycle for streaming / cancel / error / history reload."""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ConversationSource(str, enum.Enum):
    WORKSPACE = "workspace"
    CHANNEL = "channel"
    API = "api"
    WIDGET = "widget"


MAX_CONVERSATION_TITLE_LENGTH = 200
PREVIEW_CONTENT_MAX_CHARS = 240


class Conversation(Base, SoftDeleteMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_conversations_workspace_id"
        ),
        Index(
            "ix_conversations_workspace_user_updated",
            "workspace_id",
            "user_id",
            "updated_at",
        ),
        Index(
            "ix_conversations_workspace_user_pinned",
            "workspace_id",
            "user_id",
            "pinned_at",
        ),
        Index("ix_conversations_workspace_expert", "workspace_id", "expert_id"),
        Index(
            "ix_conversations_workspace_user_active",
            "workspace_id",
            "user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_conversations_workspace_source", "workspace_id", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Nullable for channel conversations (WhatsApp senders are not Geem users).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ConversationSource.WORKSPACE.value,
        server_default=ConversationSource.WORKSPACE.value,
    )
    title: Mapped[str | None] = mapped_column(String(MAX_CONVERSATION_TITLE_LENGTH), nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    favorited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    @property
    def is_pinned(self) -> bool:
        return self.pinned_at is not None

    @property
    def is_favorite(self) -> bool:
        return self.favorited_at is not None


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "id", name="uq_messages_conversation_id"
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_conversation_id", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Metadata-safe citations only. Chunk rows keep their legacy shape; MCP tool
    # rows carry kind=tool plus display-name/tool-name and never a server URL.
    citations: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Snapshot of chat composer attachments for this user turn (filename/mime; blob may TTL).
    attachments: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MessageStatus.COMPLETED.value
    )
    # Optional logical link to usage metering. Not a PostgreSQL FK: partitioned
    # ``usage_events`` primary key is ``(id, created_at)`` and cannot be
    # referenced by ``id`` alone. After raw-event retention the UUID may not
    # resolve; Message APIs must treat that as optional, not an error.
    usage_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
