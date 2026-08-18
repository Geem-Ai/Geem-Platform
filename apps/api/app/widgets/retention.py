"""Widget conversation retention — 1h message TTL + empty-thread cleanup."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from app.conversations.models import Conversation, ConversationSource, Message
from app.core.config import Settings, get_settings
from app.widgets.models import WidgetConversationBinding

logger = logging.getLogger(__name__)


class WidgetRetentionService:
    """Hard-delete widget messages older than TTL; drop empty widget threads."""

    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def cutoff(self) -> datetime:
        hours = max(1, int(self.settings.widget_message_ttl_hours))
        return datetime.now(timezone.utc) - timedelta(hours=hours)

    def purge_expired_for_conversation(self, conversation_id: uuid.UUID) -> int:
        """Eager path — drop stale messages on this widget thread before history load."""
        result = self.db.execute(
            delete(Message).where(
                Message.conversation_id == conversation_id,
                Message.created_at < self.cutoff,
            )
        )
        deleted = int(result.rowcount or 0)
        if deleted:
            self.db.flush()
        return deleted

    def purge_expired(self, *, limit: int = 500) -> dict[str, int]:
        """Periodic sweep — expire old widget messages, then empty conversations."""
        cutoff = self.cutoff
        widget_conv_ids = (
            select(Conversation.id)
            .where(Conversation.source == ConversationSource.WIDGET.value)
            .scalar_subquery()
        )
        # Cap blast radius: delete up to ``limit`` oldest expired messages first.
        expired_ids = list(
            self.db.scalars(
                select(Message.id)
                .where(
                    Message.conversation_id.in_(widget_conv_ids),
                    Message.created_at < cutoff,
                )
                .order_by(Message.created_at.asc())
                .limit(max(1, int(limit)))
            ).all()
        )
        messages_deleted = 0
        if expired_ids:
            result = self.db.execute(delete(Message).where(Message.id.in_(expired_ids)))
            messages_deleted = int(result.rowcount or 0)

        conversations_deleted = self._purge_empty_widget_conversations(limit=limit)
        self.db.commit()
        if messages_deleted or conversations_deleted:
            logger.info(
                "widget_retention_purged",
                extra={
                    "messages_deleted": messages_deleted,
                    "conversations_deleted": conversations_deleted,
                },
            )
        return {
            "messages_deleted": messages_deleted,
            "conversations_deleted": conversations_deleted,
        }

    def _purge_empty_widget_conversations(self, *, limit: int) -> int:
        has_messages = exists(
            select(Message.id).where(Message.conversation_id == Conversation.id)
        )
        empty_ids = list(
            self.db.scalars(
                select(Conversation.id)
                .where(
                    Conversation.source == ConversationSource.WIDGET.value,
                    ~has_messages,
                )
                .limit(max(1, int(limit)))
            ).all()
        )
        if not empty_ids:
            return 0
        # Bindings cascade via FK on conversation_id.
        self.db.execute(
            delete(WidgetConversationBinding).where(
                WidgetConversationBinding.conversation_id.in_(empty_ids)
            )
        )
        result = self.db.execute(
            delete(Conversation).where(Conversation.id.in_(empty_ids))
        )
        return int(result.rowcount or 0)
