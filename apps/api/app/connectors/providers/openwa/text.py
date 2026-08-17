"""Phone normalization + outbound text segmentation for OpenWA."""

from __future__ import annotations

import re

from app.connectors.providers.openwa.schemas import OPENWA_TEXT_MAX_CHARS
from app.core.errors import AppError, ErrorCategory

_NON_DIGIT = re.compile(r"\D+")


def normalize_whatsapp_phone(raw: str) -> str:
    """Digits-only international phone (no +, spaces, hyphens). 6–15 digits."""
    digits = _NON_DIGIT.sub("", (raw or "").strip())
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits.isdigit() or not (6 <= len(digits) <= 15):
        raise AppError(
            ErrorCategory.OPENWA_PHONE_INVALID,
            "Enter a valid international phone number (digits only, with country code).",
            details={"length": len(digits)},
        )
    return digits


def split_whatsapp_text(text: str, *, max_chars: int = OPENWA_TEXT_MAX_CHARS) -> list[str]:
    """Split outbound text into sequential segments ≤ max_chars.

    Prefer paragraph/newline, then sentence/space boundaries; hard-split only as
    a last resort. Operates on Unicode code points (Python str), never mid-surrogate.
    """
    content = text or ""
    if not content:
        return []
    limit = max(1, int(max_chars))
    if len(content) <= limit:
        return [content]

    segments: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= limit:
            segments.append(remaining)
            break
        window = remaining[:limit]
        split_at = _best_split(window)
        if split_at <= 0:
            split_at = limit
        piece = remaining[:split_at].rstrip()
        if not piece:
            piece = remaining[:limit]
            split_at = len(piece)
        segments.append(piece)
        remaining = remaining[split_at:].lstrip("\n")
    return segments


def _best_split(window: str) -> int:
    for sep in ("\n\n", "\n"):
        idx = window.rfind(sep)
        if idx >= max(1, len(window) // 4):
            return idx + len(sep)
    # Sentence-ish boundaries
    for sep in (". ", "! ", "? ", "۔ ", "؟ "):
        idx = window.rfind(sep)
        if idx >= max(1, len(window) // 4):
            return idx + len(sep)
    idx = window.rfind(" ")
    if idx >= max(1, len(window) // 4):
        return idx + 1
    return 0
