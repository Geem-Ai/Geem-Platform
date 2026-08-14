"""Strict validation for chat composer uploads (security-focused).

Rules:
- Hard size cap (default 5 MiB) before/while reading
- Extension allowlist only (pdf / txt / md)
- Content must match extension (PDF magic; UTF-8 text without NULs)
- Filename sanitized; path components stripped
- Declared Content-Type is advisory only and must not expand the allowlist
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.ingestion.pdf_utils import validate_pdf_bytes

_ALLOWED_EXTENSIONS = frozenset({".pdf", ".txt", ".text", ".md", ".markdown", ".mdown", ".mkd"})
_FILENAME_SAFE = re.compile(r"[^\w.\-()\u0600-\u06FF ]+")


@dataclass(frozen=True, slots=True)
class ChatAttachmentInspection:
    safe_name: str
    mime_type: str
    extension: str
    sha256: str
    byte_size: int


def sanitize_attachment_filename(name: str) -> str:
    base = PurePosixPath((name or "").replace("\x00", "")).name
    base = _FILENAME_SAFE.sub("_", base).strip().strip(".")
    return base[:200] or "attachment.bin"


def _require_utf8_text(file_bytes: bytes) -> None:
    if b"\x00" in file_bytes:
        raise AppError(
            ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
            "Unsupported document type. Allowed: PDF, plain text, Markdown.",
            details={"reason": "nul_byte_in_text"},
        )
    try:
        file_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError(
            ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
            "Unsupported document type. Allowed: PDF, plain text, Markdown.",
            details={"reason": "invalid_utf8"},
        ) from exc


def inspect_chat_attachment(
    file_bytes: bytes,
    filename: str,
    *,
    settings: Settings,
    declared_mime_type: str | None = None,
) -> ChatAttachmentInspection:
    max_bytes = settings.chat_attachment_max_bytes
    size = len(file_bytes)
    if size == 0:
        raise AppError(ErrorCategory.INVALID_DOCUMENT, "Empty uploads are not allowed.")
    if size > max_bytes:
        raise AppError(
            ErrorCategory.UPLOAD_TOO_LARGE,
            f"Upload exceeds maximum size of {max_bytes} bytes",
            details={"max_bytes": max_bytes, "byte_size": size},
        )

    safe_name = sanitize_attachment_filename(filename)
    ext = PurePosixPath(safe_name).suffix.lower()
    declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()

    if ext not in _ALLOWED_EXTENSIONS:
        raise AppError(
            ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
            "Unsupported document type. Allowed: PDF, plain text, Markdown.",
            details={"filename": safe_name, "declared_mime_type": declared_mime_type},
        )

    if ext == ".pdf":
        # Require magic bytes — do not trust extension or Content-Type alone.
        if not file_bytes.startswith(b"%PDF"):
            raise AppError(
                ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
                "Unsupported document type. Allowed: PDF, plain text, Markdown.",
                details={"reason": "pdf_magic_mismatch", "declared_mime_type": declared},
            )
        validate_pdf_bytes(
            file_bytes,
            max_bytes=max_bytes,
            max_pages=min(settings.max_pdf_pages, 50),
        )
        mime = "application/pdf"
        storage_ext = "pdf"
    elif ext in {".md", ".markdown", ".mdown", ".mkd"}:
        _require_utf8_text(file_bytes)
        mime = "text/markdown"
        storage_ext = "md"
    else:
        _require_utf8_text(file_bytes)
        mime = "text/plain"
        storage_ext = "txt"

    digest = hashlib.sha256(file_bytes).hexdigest()
    return ChatAttachmentInspection(
        safe_name=safe_name,
        mime_type=mime,
        extension=storage_ext,
        sha256=digest,
        byte_size=size,
    )
