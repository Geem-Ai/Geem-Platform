from __future__ import annotations

import re

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

# Subdomain-safe: lowercase letters, digits, hyphens; 3–63 chars; no leading/trailing hyphen.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])$")


def normalize_slug(raw: str) -> str:
    return raw.strip().lower()


def validate_workspace_slug(raw: str, *, settings: Settings | None = None) -> str:
    """Normalize and validate a workspace slug. Raises AppError on failure."""
    cfg = settings or get_settings()
    slug = normalize_slug(raw)
    if not slug or not _SLUG_RE.match(slug):
        raise AppError(
            ErrorCategory.WORKSPACE_SLUG_INVALID,
            "Workspace slug must be 3–63 characters, lowercase alphanumeric, "
            "hyphens allowed only between characters.",
            details={"slug": slug},
        )
    if slug in cfg.reserved_slugs:
        raise AppError(
            ErrorCategory.WORKSPACE_SLUG_INVALID,
            "This workspace slug is reserved.",
            details={"slug": slug},
        )
    return slug
