"""Chat composer attachments — ephemeral Workspace blobs (not RAG Documents).

Stored for later chat turns; not ingested into Expert knowledge.
Auto-expire after ``Settings.chat_attachment_ttl_hours`` (default 12h).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChatAttachment(Base):
    """User-owned chat attachment inside a Workspace.

    Visibility is private to ``uploaded_by`` within ``workspace_id`` until a
    later phase links attachments to Messages. Rows past ``expires_at`` are
    purged by Celery (scheduled + periodic sweep).
    """

    __tablename__ = "chat_attachments"
    __table_args__ = (
        Index("ix_chat_attachments_workspace_user", "workspace_id", "uploaded_by"),
        Index("ix_chat_attachments_workspace_created", "workspace_id", "created_at"),
        Index("ix_chat_attachments_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
