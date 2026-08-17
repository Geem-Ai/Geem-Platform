"""Supported Google Drive MIME types and export mapping (Phase 9D)."""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory

MIME_PDF = "application/pdf"
MIME_PLAIN = "text/plain"
MIME_MARKDOWN = "text/markdown"
MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_GOOGLE_SLIDES = "application/vnd.google-apps.presentation"

SUPPORTED_BINARY_MIMES: frozenset[str] = frozenset(
    {MIME_PDF, MIME_PLAIN, MIME_MARKDOWN}
)
EXPORT_FALLBACK_MIME = MIME_PLAIN
EXPORT_PREFERRED_MIME = MIME_MARKDOWN

UNSUPPORTED_WORKSPACE_MIMES: frozenset[str] = frozenset(
    {MIME_GOOGLE_SHEET, MIME_GOOGLE_SLIDES}
)


def is_google_workspace_doc(mime_type: str | None) -> bool:
    return (mime_type or "").strip() == MIME_GOOGLE_DOC


def is_supported_mime(mime_type: str | None) -> bool:
    mime = (mime_type or "").strip()
    if not mime:
        return False
    if mime in UNSUPPORTED_WORKSPACE_MIMES:
        return False
    return mime in SUPPORTED_BINARY_MIMES or mime == MIME_GOOGLE_DOC


def require_supported_mime(mime_type: str | None) -> str:
    mime = (mime_type or "").strip()
    if not is_supported_mime(mime):
        raise AppError(
            ErrorCategory.GOOGLE_DRIVE_FILE_TYPE_UNSUPPORTED,
            "This Google Drive file type is not supported.",
            details={"mime_type": mime or None},
        )
    return mime


def export_mime_for(mime_type: str | None) -> str:
    """Return Drive export MIME for Google Docs; raise for non-exportable types."""
    mime = require_supported_mime(mime_type)
    if mime == MIME_GOOGLE_DOC:
        return EXPORT_PREFERRED_MIME
    raise AppError(
        ErrorCategory.GOOGLE_DRIVE_FILE_TYPE_UNSUPPORTED,
        "File does not require Google Workspace export.",
        details={"mime_type": mime},
    )


def suggested_filename(name: str | None, mime_type: str | None) -> str:
    base = (name or "drive-file").strip() or "drive-file"
    # Strip path separators from provider names.
    base = base.replace("/", "_").replace("\\", "_")
    mime = (mime_type or "").strip()
    lower = base.lower()
    if mime == MIME_PDF and not lower.endswith(".pdf"):
        return f"{base}.pdf"
    if mime == MIME_PLAIN and not (lower.endswith(".txt") or lower.endswith(".text")):
        return f"{base}.txt"
    if mime in {MIME_MARKDOWN, MIME_GOOGLE_DOC} and not (
        lower.endswith(".md") or lower.endswith(".markdown")
    ):
        return f"{base}.md"
    return base
