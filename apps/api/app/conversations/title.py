"""Conversation titles — post-turn LLM naming (Phase 4 polish).

After the first successful turn, title generation runs in the background
(Celery, with a thread fallback) so the chat lock and SSE stream are not held
open for the LLM call. The client discovers the title via conversation refetch.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.openrouter.client import OpenRouterClient

logger = logging.getLogger(__name__)

DEFAULT_TITLE_MAX_LENGTH = 80
_TITLE_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "conversation_title_v1.txt"
)


def derive_conversation_title(
    text: str,
    *,
    max_length: int = DEFAULT_TITLE_MAX_LENGTH,
) -> str:
    """Build a sidebar-friendly title from the first user message (no LLM)."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if max_length < 1:
        return cleaned
    if len(cleaned) <= max_length:
        return cleaned

    truncated = cleaned[:max_length]
    # Prefer a word boundary when it still leaves a meaningful prefix.
    if " " in truncated:
        candidate = truncated.rsplit(" ", 1)[0].rstrip(".,;:!?،؛")
        if len(candidate) >= max(8, max_length // 3):
            return f"{candidate}…"
    return f"{truncated.rstrip()}…"


def sanitize_generated_title(
    text: str,
    *,
    max_length: int = DEFAULT_TITLE_MAX_LENGTH,
) -> str:
    """Normalize LLM output into a single-line sidebar title."""
    cleaned = (text or "").strip()
    cleaned = cleaned.strip("\"'`“”‘’")
    cleaned = re.sub(r"^(title|عنوان)\s*[:：\-–—]\s*", "", cleaned, flags=re.I)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return ""
    if max_length >= 1 and len(cleaned) > max_length:
        return derive_conversation_title(cleaned, max_length=max_length)
    return cleaned


def generate_conversation_title(
    *,
    user_message: str,
    assistant_message: str | None = None,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
) -> str:
    """Call the LLM for a short title; fall back to deterministic trim on failure."""
    cfg = settings or get_settings()
    max_len = int(cfg.conversation_title_max_length or DEFAULT_TITLE_MAX_LENGTH)
    fallback = derive_conversation_title(user_message, max_length=max_len)

    try:
        prompt = _TITLE_PROMPT_PATH.read_text(encoding="utf-8").strip()
        or_client = client or OpenRouterClient(cfg)
        model = (cfg.openrouter_general_model or "").strip() or cfg.openrouter_chat_model
        user_parts = [f"User message:\n{(user_message or '').strip()[:2000]}"]
        assistant = (assistant_message or "").strip()
        if assistant:
            user_parts.append(f"Assistant reply (excerpt):\n{assistant[:800]}")
        user_parts.append("Title:")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            "stream": False,
            "max_tokens": 64,
            "temperature": 0.3,
            "provider": or_client.provider_preferences(),
        }
        body, _meta, status = or_client.request(
            "POST",
            "/chat/completions",
            json_body=payload,
            timeout=30.0,
            max_attempts=2,
        )
        if status >= 400 or not body:
            logger.warning("conversation_title_llm_http status=%s", status)
            return fallback
        choices = body.get("choices") or []
        if not choices:
            return fallback
        content = (choices[0].get("message", {}) or {}).get("content") or ""
        titled = sanitize_generated_title(content, max_length=max_len)
        return titled or fallback
    except Exception:  # noqa: BLE001 — never fail the chat turn for titling
        logger.exception("conversation_title_llm_failed")
        return fallback


def persist_generated_conversation_title(
    *,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message: str,
    assistant_message: str,
    settings: Settings | None = None,
) -> str | None:
    """Generate and commit a title on a fresh DB session (safe after lock release)."""
    from app.conversations.models import Conversation
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        conv = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        if conv is None:
            return None
        if (conv.title or "").strip():
            return conv.title
        titled = generate_conversation_title(
            user_message=user_message,
            assistant_message=assistant_message,
            settings=settings or get_settings(),
        )
        if not titled:
            return None
        conv.title = titled
        conv.updated_at = datetime.now(timezone.utc)
        db.commit()
        return titled
    except Exception:  # noqa: BLE001 — background job must not raise to callers
        logger.exception(
            "conversation_title_persist_failed conversation_id=%s",
            conversation_id,
        )
        db.rollback()
        return None
    finally:
        db.close()


def schedule_conversation_title(
    *,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message: str,
    assistant_message: str,
) -> None:
    """Enqueue title generation after the chat lock is released.

    Tries Celery first so API workers stay free. Always also starts a short
    delayed in-process backup: ``.delay()`` succeeds even when the worker is
    stale/missing the task registry, which previously left chats untitled.
    ``persist_generated_conversation_title`` is idempotent if a title exists.
    """
    kwargs = {
        "conversation_id": conversation_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "user_message": user_message,
        "assistant_message": assistant_message,
    }
    try:
        from app.worker.tasks import generate_conversation_title_task

        generate_conversation_title_task.delay(
            conversation_id=str(conversation_id),
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "conversation_title_celery_schedule_failed conversation_id=%s",
            conversation_id,
        )

    def _backup() -> None:
        # Give a healthy Celery worker a head start; then fill in if still untitled.
        import time

        time.sleep(1.5)
        persist_generated_conversation_title(**kwargs)

    threading.Thread(
        target=_backup,
        name=f"conversation-title-{conversation_id}",
        daemon=True,
    ).start()


__all__ = [
    "DEFAULT_TITLE_MAX_LENGTH",
    "derive_conversation_title",
    "generate_conversation_title",
    "persist_generated_conversation_title",
    "sanitize_generated_title",
    "schedule_conversation_title",
]
