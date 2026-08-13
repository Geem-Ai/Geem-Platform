"""Public ``/api/v1/chat`` request/response DTOs."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas import Citation


class PublicChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expert_id: uuid.UUID
    message: str
    stream: bool = False

    @field_validator("message")
    @classmethod
    def message_present(cls, value: str) -> str:
        # Length/trim rules are applied by shared Chat validation so the
        # established Workspace Chat limit stays the source of truth.
        if value is None or not str(value).strip():
            raise ValueError("Message content is required.")
        return value


class PublicChatUsage(BaseModel):
    billed_tokens: int = 0


class PublicChatResponse(BaseModel):
    id: str
    expert_id: uuid.UUID
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    usage: PublicChatUsage
