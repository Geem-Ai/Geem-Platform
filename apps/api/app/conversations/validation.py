"""Shared Chat message validation (Workspace Chat + public API)."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory


def validate_chat_message(content: str, *, settings: Settings | None = None) -> str:
    """Trim and enforce the established Chat prompt length."""
    cfg = settings or get_settings()
    question = (content or "").strip()
    if not question:
        raise AppError(ErrorCategory.VALIDATION, "Message content is required.")
    max_chars = cfg.max_chat_message_chars
    if len(question) > max_chars:
        raise AppError(
            ErrorCategory.VALIDATION,
            f"Message exceeds maximum length of {max_chars} characters.",
        )
    return question
