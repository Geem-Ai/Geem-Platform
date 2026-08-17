"""Conversation / Message API schemas (Phase 4A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.schemas import Citation
from app.conversations.models import MAX_CONVERSATION_TITLE_LENGTH


class ConversationMessageStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=32_000)
    attachment_id: uuid.UUID | None = None

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        return (value or "").strip()

    @model_validator(mode="after")
    def _require_content_or_attachment(self) -> ConversationMessageStreamRequest:
        if not self.content and self.attachment_id is None:
            raise ValueError("Message content or attachment_id is required.")
        return self


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expert_id: uuid.UUID
    title: str | None = Field(default=None, max_length=MAX_CONVERSATION_TITLE_LENGTH)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ConversationUpdateRequest(BaseModel):
    """Rename and/or pin/favorite. Expert is immutable once the conversation exists."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=MAX_CONVERSATION_TITLE_LENGTH)
    is_pinned: bool | None = None
    is_favorite: bool | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ConversationClearHistoryOut(BaseModel):
    deleted_count: int


class ConversationExpertSummary(BaseModel):
    """Safe Expert summary for Chat sidebar / conversation detail.

    Intentionally omits ``system_instructions``, ``rag_config``, and knowledge
    inventory — Platform Expert privacy from Phase 3 must remain intact.
    """

    id: uuid.UUID
    type: str
    ownership: str
    name: str
    description: str | None = None
    icon_url: str | None = None
    status: str
    visibility: str
    knowledge_mode: str = "rag"


class MessagePreviewOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class MessageAttachmentOut(BaseModel):
    id: uuid.UUID | str
    filename: str
    mime_type: str
    byte_size: int = 0


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    attachments: list[MessageAttachmentOut] = Field(default_factory=list)
    status: str
    usage_event_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("attachments", mode="before")
    @classmethod
    def _coerce_attachments(cls, value: Any) -> Any:
        if value is None:
            return []
        return value


class ConversationOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    expert_id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    is_pinned: bool
    pinned_at: datetime | None
    is_favorite: bool = False
    favorited_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    expert: ConversationExpertSummary | None = None
    last_message: MessagePreviewOut | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailOut(ConversationOut):
    """Detail without embedded messages — use ``GET .../messages`` for history."""

    pass
