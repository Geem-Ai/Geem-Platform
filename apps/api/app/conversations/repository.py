"""Conversation data access — always scoped by workspace_id + user_id."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.conversations.models import Conversation, Message, MessageStatus
from app.experts.models import Expert


class ConversationRepository:
    """Unsafe lookups by conversation id alone are intentionally absent."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_user(
        self,
        *,
        conversation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
            Conversation.user_id == user_id,
        )
        if not include_deleted:
            stmt = stmt.where(Conversation.deleted_at.is_(None))
        return self.db.scalar(stmt)

    def list_for_user(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Conversation]:
        """Pinned first (pinned_at DESC), then recent (updated_at DESC)."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(
                case((Conversation.pinned_at.is_(None), 1), else_=0).asc(),
                Conversation.pinned_at.desc().nulls_last(),
                Conversation.updated_at.desc(),
            )
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def create(self, conversation: Conversation) -> Conversation:
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def soft_delete(self, conversation: Conversation, when: datetime | None = None) -> None:
        conversation.soft_delete(when=when)
        self.db.flush()

    def list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def get_message(
        self,
        message_id: uuid.UUID,
        *,
        conversation_id: uuid.UUID,
    ) -> Message | None:
        return self.db.scalar(
            select(Message).where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
            )
        )

    def has_active_generation(self, conversation_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(Message.id)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.role == "assistant",
                    Message.status.in_(("pending", "streaming")),
                )
                .limit(1)
            )
            is not None
        )

    def cancel_stale_generations(
        self,
        conversation_id: uuid.UUID,
        *,
        older_than: datetime,
    ) -> int:
        """Mark abandoned pending/streaming assistants as cancelled.

        Used when a worker crashes after inserting ``streaming`` but before
        settle — otherwise ``has_active_generation`` blocks the conversation
        forever after the Redis lock TTL expires.
        """
        rows = list(
            self.db.scalars(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.role == "assistant",
                    Message.status.in_(
                        (MessageStatus.PENDING.value, MessageStatus.STREAMING.value)
                    ),
                    Message.updated_at < older_than,
                )
            )
        )
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        for msg in rows:
            msg.status = MessageStatus.CANCELLED.value
            msg.updated_at = now
        self.db.flush()
        return len(rows)

    def get_latest_assistant_message(self, conversation_id: uuid.UUID) -> Message | None:
        return self.db.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )

    def find_preceding_user_message(
        self, conversation_id: uuid.UUID, assistant: Message
    ) -> Message | None:
        return self.db.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.created_at <= assistant.created_at,
                Message.id != assistant.id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )

    def list_history_for_rag(
        self,
        conversation_id: uuid.UUID,
        *,
        before_message_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """Completed user/assistant turns before the current turn, oldest first."""
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role.in_(("user", "assistant")),
                Message.status == "completed",
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
        )
        if before_message_id is not None:
            # Exclude the current user message and anything after it.
            pivot = self.db.scalar(
                select(Message).where(
                    Message.id == before_message_id,
                    Message.conversation_id == conversation_id,
                )
            )
            if pivot is not None:
                stmt = stmt.where(
                    (Message.created_at < pivot.created_at)
                    | (
                        (Message.created_at == pivot.created_at)
                        & (Message.id < pivot.id)
                    )
                )
        rows = list(self.db.scalars(stmt.limit(limit)))
        rows.reverse()
        return rows

    def create_message(self, message: Message) -> Message:
        self.db.add(message)
        self.db.flush()
        return message

    def get_latest_messages_by_conversation(
        self, conversation_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Message]:
        """One latest message per conversation (PostgreSQL DISTINCT ON)."""
        if not conversation_ids:
            return {}
        rows = list(
            self.db.scalars(
                select(Message)
                .distinct(Message.conversation_id)
                .where(Message.conversation_id.in_(conversation_ids))
                .order_by(Message.conversation_id, Message.created_at.desc(), Message.id.desc())
            )
        )
        return {m.conversation_id: m for m in rows}

    def get_experts_by_ids(self, expert_ids: list[uuid.UUID]) -> dict[uuid.UUID, Expert]:
        if not expert_ids:
            return {}
        rows = list(
            self.db.scalars(
                select(Expert).where(
                    Expert.id.in_(expert_ids),
                    Expert.deleted_at.is_(None),
                )
            )
        )
        return {e.id: e for e in rows}

    def get_experts_by_ids_including_deleted(
        self, expert_ids: set[uuid.UUID] | list[uuid.UUID]
    ) -> dict[uuid.UUID, Expert]:
        if not expert_ids:
            return {}
        rows = list(self.db.scalars(select(Expert).where(Expert.id.in_(expert_ids))))
        return {e.id: e for e in rows}

    def get_expert_including_deleted(self, expert_id: uuid.UUID) -> Expert | None:
        return self.db.scalar(select(Expert).where(Expert.id == expert_id))
