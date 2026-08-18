"""Centralized invitation acceptance URL generation."""

from __future__ import annotations

from urllib.parse import urlencode

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

# Phase 10B will mount this SPA route. 10A only generates the URL.
ACCEPT_PATH = "/invitations/accept"


def invitation_accept_url(raw_token: str, *, settings: Settings) -> str:
    """Build ``{workspace_web}/invitations/accept?token=...``.

    Uses ``Settings.effective_workspace_web_url``. Never hardcode production hosts.
    """
    base = (settings.effective_workspace_web_url or "").rstrip("/")
    if not base:
        raise AppError(
            ErrorCategory.EMAIL_DELIVERY_FAILED,
            "Workspace web URL is not configured.",
        )
    query = urlencode({"token": raw_token})
    return f"{base}{ACCEPT_PATH}?{query}"
