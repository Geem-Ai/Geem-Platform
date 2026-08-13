"""Attribution attached to ``usage_events`` for Chat/RAG generations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class GenerationUsageContext:
    """Commercial + actor attribution for a billable (or diagnostic) generation."""

    workspace_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    expert_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    request_id: str | None = None
    extra_billed_tokens: int = 0

    def add_billed(self, tokens: int) -> None:
        self.extra_billed_tokens += max(0, int(tokens))
