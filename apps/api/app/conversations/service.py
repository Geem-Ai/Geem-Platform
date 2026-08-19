"""Conversation domain service (Phase 4A).

Orchestrates scoped repository access + ExpertAccessService for create.
Does not stream RAG — that is Phase 4B.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.schemas import Citation
from app.audit import AuditAction, AuditEntityType, record_audit
from app.common.security_log import security_log
from app.conversations.models import (
    PREVIEW_CONTENT_MAX_CHARS,
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from app.conversations.policy import ConversationAction, ConversationPolicy
from app.conversations.repository import ConversationRepository
from app.conversations.schemas import (
    ConversationExpertSummary,
    ConversationOut,
    MessageOut,
    MessagePreviewOut,
)
from app.core.errors import AppError, ErrorCategory
from app.experts.access import ExpertAccessService
from app.experts.models import Expert, ExpertType
from app.experts.policy import ExpertAction
from app.identity.models import User
from app.workspaces.models import Workspace, WorkspaceMembership


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ConversationRepository(db)
        self.expert_access = ExpertAccessService(db)

    # ------------------------------------------------------------------
    # Create / list / get / update / delete
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        expert_id: uuid.UUID,
        title: str | None = None,
    ) -> Conversation:
        ConversationPolicy.require(membership, ConversationAction.CREATE)

        # Resolve Expert through existing access layer (Workspace + Platform grants).
        auth = self.expert_access.resolve_for_workspace(
            workspace=workspace,
            membership=membership,
            expert_id=expert_id,
            action=ExpertAction.USE,
            actor_id=actor.id,
        )

        conversation = Conversation(
            workspace_id=workspace.id,
            expert_id=auth.expert.id,
            user_id=actor.id,
            title=title,
        )
        self.repo.create(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def list_for_actor(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        limit: int | None = 100,
        offset: int = 0,
    ) -> list[ConversationOut]:
        ConversationPolicy.require(membership, ConversationAction.VIEW)
        rows = self.repo.list_for_user(
            workspace_id=workspace.id,
            user_id=actor.id,
            limit=limit,
            offset=offset,
        )
        return self._serialize_many(rows)

    def get_for_actor(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
    ) -> ConversationOut:
        ConversationPolicy.require(membership, ConversationAction.VIEW)
        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            user_id=actor.id,
            actor_id=actor.id,
        )
        return self._serialize_one(conversation)

    def update(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
        title: str | None = None,
        title_provided: bool = False,
        is_pinned: bool | None = None,
        is_favorite: bool | None = None,
    ) -> Conversation:
        ConversationPolicy.require(membership, ConversationAction.UPDATE)
        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            user_id=actor.id,
            actor_id=actor.id,
        )

        changed = False
        if title_provided and conversation.title != title:
            conversation.title = title
            changed = True
        if is_pinned is True:
            if conversation.pinned_at is None:
                conversation.pinned_at = datetime.now(timezone.utc)
                changed = True
        elif is_pinned is False:
            if conversation.pinned_at is not None:
                conversation.pinned_at = None
                changed = True
        if is_favorite is True:
            if conversation.favorited_at is None:
                conversation.favorited_at = datetime.now(timezone.utc)
                changed = True
        elif is_favorite is False:
            if conversation.favorited_at is not None:
                conversation.favorited_at = None
                changed = True

        if not changed:
            return conversation

        conversation.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def soft_delete(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
    ) -> None:
        ConversationPolicy.require(membership, ConversationAction.DELETE)
        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            user_id=actor.id,
            actor_id=actor.id,
        )
        self.repo.soft_delete(conversation)
        record_audit(
            self.db,
            action=AuditAction.CONVERSATION_SOFT_DELETED,
            entity_type=AuditEntityType.CONVERSATION,
            entity_id=conversation.id,
            workspace_id=workspace.id,
            actor_user_id=actor.id,
        )
        self.db.commit()

    def clear_history(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
    ) -> int:
        """Soft-delete all of the actor's conversations in this workspace."""
        ConversationPolicy.require(membership, ConversationAction.DELETE)
        deleted = self.repo.soft_delete_all_for_user(
            workspace_id=workspace.id,
            user_id=actor.id,
        )
        self.db.commit()
        return deleted

    def list_messages(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MessageOut]:
        ConversationPolicy.require(membership, ConversationAction.LIST_MESSAGES)
        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            user_id=actor.id,
            actor_id=actor.id,
        )
        messages = self.repo.list_messages(
            conversation.id, limit=limit, offset=offset
        )
        return [self._message_out(m) for m in messages]

    # ------------------------------------------------------------------
    # Message helpers (for Phase 4B + tests) — not exposed as public write API yet
    # ------------------------------------------------------------------

    def append_message(
        self,
        *,
        workspace: Workspace,
        membership: WorkspaceMembership,
        actor: User,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | list[Citation] | None = None,
        status: str = MessageStatus.COMPLETED.value,
        usage_event_id: uuid.UUID | None = None,
    ) -> Message:
        """Append a message to an owned conversation.

        Used by Phase 4B orchestration and Phase 4A persistence tests.
        Expert on the conversation is immutable once messages exist — callers
        must not reassign ``expert_id``; selecting another Expert starts a new
        Conversation.
        """
        ConversationPolicy.require(membership, ConversationAction.UPDATE)
        conversation = self._require_owned(
            conversation_id=conversation_id,
            workspace_id=workspace.id,
            user_id=actor.id,
            actor_id=actor.id,
        )
        if role not in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid message role.")
        if status not in {s.value for s in MessageStatus}:
            raise AppError(ErrorCategory.VALIDATION, "Invalid message status.")

        safe_citations = self.normalize_citations(citations)
        if role == MessageRole.USER.value and safe_citations:
            raise AppError(
                ErrorCategory.VALIDATION,
                "User messages cannot carry citations.",
            )

        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content or "",
            citations=safe_citations,
            status=status,
            usage_event_id=usage_event_id,
        )
        self.repo.create_message(message)
        conversation.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(message)
        return message

    @staticmethod
    def normalize_citations(
        citations: list[dict[str, Any]] | list[Citation] | None,
    ) -> list[dict[str, Any]]:
        """Persist only the Phase 3 metadata-safe citation contract."""
        if not citations:
            return []
        out: list[dict[str, Any]] = []
        for item in citations:
            try:
                if isinstance(item, Citation):
                    parsed = item
                else:
                    parsed = Citation.model_validate(item)
            except ValidationError as exc:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    "Invalid citation payload.",
                    details={"errors": exc.errors()},
                ) from exc
            out.append(parsed.model_dump(mode="json"))
        return out

    def to_out(self, conversation: Conversation) -> ConversationOut:
        return self._serialize_one(conversation)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_owned(
        self,
        *,
        conversation_id: uuid.UUID,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> Conversation:
        conversation = self.repo.get_for_user(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if conversation is None:
            security_log(
                "conversation_access_denied",
                conversation_id=str(conversation_id),
                workspace_id=str(workspace_id),
                actor_id=str(actor_id),
                reason="missing_or_cross_scope",
            )
            raise AppError(ErrorCategory.CONVERSATION_NOT_FOUND, "Conversation not found.")
        return conversation

    def _serialize_many(self, rows: list[Conversation]) -> list[ConversationOut]:
        if not rows:
            return []
        expert_map = self.repo.get_experts_by_ids([c.expert_id for c in rows])
        # Soft-deleted experts may still be needed for history display.
        missing_ids = {c.expert_id for c in rows if c.expert_id not in expert_map}
        if missing_ids:
            expert_map.update(self.repo.get_experts_by_ids_including_deleted(missing_ids))
        last_map = self.repo.get_latest_messages_by_conversation([c.id for c in rows])
        return [
            self._build_out(
                c,
                expert=expert_map.get(c.expert_id),
                last_message=last_map.get(c.id),
            )
            for c in rows
        ]

    def _serialize_one(self, conversation: Conversation) -> ConversationOut:
        expert = self.repo.get_experts_by_ids([conversation.expert_id]).get(
            conversation.expert_id
        )
        if expert is None:
            expert = self.repo.get_expert_including_deleted(conversation.expert_id)
        last_map = self.repo.get_latest_messages_by_conversation([conversation.id])
        return self._build_out(
            conversation,
            expert=expert,
            last_message=last_map.get(conversation.id),
        )

    def _build_out(
        self,
        conversation: Conversation,
        *,
        expert: Expert | None,
        last_message: Message | None,
    ) -> ConversationOut:
        return ConversationOut(
            id=conversation.id,
            workspace_id=conversation.workspace_id,
            expert_id=conversation.expert_id,
            user_id=conversation.user_id,
            title=conversation.title,
            is_pinned=conversation.is_pinned,
            pinned_at=conversation.pinned_at,
            is_favorite=conversation.is_favorite,
            favorited_at=conversation.favorited_at,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            expert=self._expert_summary(expert) if expert else None,
            last_message=self._preview(last_message) if last_message else None,
        )

    @staticmethod
    def _expert_summary(expert: Expert) -> ConversationExpertSummary:
        ownership = (
            "platform"
            if expert.type == ExpertType.PLATFORM.value
            else "workspace"
        )
        return ConversationExpertSummary(
            id=expert.id,
            type=expert.type,
            ownership=ownership,
            name=expert.name,
            description=expert.description,
            icon_url=expert.icon_url,
            status=expert.status,
            visibility=expert.visibility,
            knowledge_mode=getattr(expert, "knowledge_mode", None) or "rag",
        )

    @staticmethod
    def _preview(message: Message) -> MessagePreviewOut:
        content = message.content or ""
        if len(content) > PREVIEW_CONTENT_MAX_CHARS:
            content = content[: PREVIEW_CONTENT_MAX_CHARS - 1] + "…"
        return MessagePreviewOut(
            id=message.id,
            role=message.role,
            content=content,
            created_at=message.created_at,
        )

    @staticmethod
    def _message_out(message: Message) -> MessageOut:
        citations: list[Citation] = []
        for item in message.citations or []:
            try:
                citations.append(Citation.model_validate(item))
            except ValidationError:
                continue
        return MessageOut(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            citations=citations,
            status=message.status,
            usage_event_id=message.usage_event_id,
            created_at=message.created_at,
            updated_at=message.updated_at,
        )
