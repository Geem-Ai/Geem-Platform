"""Typed App Store commercial errors (Phase 9B)."""

from __future__ import annotations

# Re-export convenience — categories live in app.core.errors.
from app.core.errors import AppError, ErrorCategory

__all__ = ["AppError", "ErrorCategory"]
