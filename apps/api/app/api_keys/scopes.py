"""API-key scope allowlist (Phase 7A)."""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory

SCOPE_CHAT_WRITE = "chat:write"
ALLOWED_SCOPES: frozenset[str] = frozenset({SCOPE_CHAT_WRITE})
DEFAULT_SCOPES: tuple[str, ...] = (SCOPE_CHAT_WRITE,)


def normalize_scopes(scopes: list[str] | None) -> list[str]:
    """Trim, drop empties, de-duplicate (first-seen order), reject unknown.

    ``None`` or ``[]`` defaults to ``[chat:write]``.
    """
    if not scopes:
        return list(DEFAULT_SCOPES)

    seen: set[str] = set()
    normalized: list[str] = []
    unknown: list[str] = []
    for raw in scopes:
        value = (raw or "").strip()
        if not value:
            continue
        if value not in ALLOWED_SCOPES:
            if value not in unknown:
                unknown.append(value)
            continue
        if value not in seen:
            seen.add(value)
            normalized.append(value)

    if unknown:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Unknown API key scope.",
            details={"unknown_scopes": unknown, "allowed_scopes": sorted(ALLOWED_SCOPES)},
        )
    if not normalized:
        return list(DEFAULT_SCOPES)
    return normalized
