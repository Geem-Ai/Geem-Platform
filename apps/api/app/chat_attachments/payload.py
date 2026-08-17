"""Ephemeral chat-turn attachment payload for OpenRouter multimodal messages."""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChatTurnAttachment:
    """Bytes already loaded from MinIO for a single chat turn (not Expert ingest)."""

    id: uuid.UUID
    filename: str
    mime_type: str
    byte_size: int
    data: bytes

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "filename": self.filename,
            "mime_type": self.mime_type,
            "byte_size": self.byte_size,
        }

    def data_url(self) -> str:
        b64 = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{b64}"


def openrouter_attachment_parts(attachment: ChatTurnAttachment) -> list[dict[str, Any]]:
    """Build OpenRouter content parts for a chat attachment (no file-parser plugin)."""
    mime = (attachment.mime_type or "").lower()
    if mime.startswith("image/"):
        return [
            {
                "type": "image_url",
                "image_url": {"url": attachment.data_url()},
            }
        ]
    if mime == "application/pdf":
        return [
            {
                "type": "file",
                "file": {
                    "filename": attachment.filename,
                    "file_data": attachment.data_url(),
                },
            }
        ]
    # text/plain, text/markdown — inline as text (UTF-8 already validated on upload)
    text = attachment.data.decode("utf-8")
    label = attachment.filename or "attachment"
    return [{"type": "text", "text": f"Attached file ({label}):\n{text}"}]


def build_user_message_content(
    text: str,
    attachment: ChatTurnAttachment | None,
) -> str | list[dict[str, Any]]:
    """Return a string (text-only) or multimodal content array for the user message."""
    if attachment is None:
        return text
    parts: list[dict[str, Any]] = []
    if text.strip():
        parts.append({"type": "text", "text": text})
    parts.extend(openrouter_attachment_parts(attachment))
    return parts
