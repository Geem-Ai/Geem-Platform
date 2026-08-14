"""OpenAI-compatible public Chat Completions + Models DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas import Citation
from app.common.public_model import PUBLIC_MODEL_ID


class ChatCompletionMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: Any = None


class ChatCompletionRequest(BaseModel):
    """Permissive OpenAI Chat Completions body. Unknown keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    model: str = PUBLIC_MODEL_ID
    messages: list[ChatCompletionMessage] = Field(default_factory=list)
    stream: bool = False


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionChoiceMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage
    citations: list[Citation] = Field(default_factory=list)


class ModelObject(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelObject] = Field(default_factory=list)
