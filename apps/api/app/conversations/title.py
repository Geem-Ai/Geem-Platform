"""Deterministic conversation titles from the first user message (Phase 4B).

No LLM call — trim, normalize whitespace, enforce max length, preserve Unicode.
Swap this module later for AI titling without changing Conversation APIs.
"""

from __future__ import annotations

DEFAULT_TITLE_MAX_LENGTH = 80


def derive_conversation_title(
    text: str,
    *,
    max_length: int = DEFAULT_TITLE_MAX_LENGTH,
) -> str:
    """Build a sidebar-friendly title from the first user message."""
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
