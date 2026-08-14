"""Schemas for chat voice transcription."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatTranscribeOut(BaseModel):
    text: str = Field(..., description="Transcribed text for the chat composer.")
    duration_seconds: float | None = Field(
        default=None,
        description="Audio duration in seconds when reported by the provider.",
    )
