"""Supported OneDrive MIME / extensions and Graph PDF conversion (Phase 9E)."""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory

MIME_PDF = "application/pdf"
MIME_PLAIN = "text/plain"
MIME_MARKDOWN = "text/markdown"

# Office formats converted to PDF via Graph content?format=pdf
MIME_DOC = "application/msword"
MIME_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
MIME_PPT = "application/vnd.ms-powerpoint"
MIME_PPTX = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
MIME_XLS = "application/vnd.ms-excel"
MIME_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

DIRECT_MIMES: frozenset[str] = frozenset({MIME_PDF, MIME_PLAIN, MIME_MARKDOWN})
CONVERT_TO_PDF_MIMES: frozenset[str] = frozenset(
    {MIME_DOC, MIME_DOCX, MIME_PPT, MIME_PPTX, MIME_XLS, MIME_XLSX}
)

_EXT_TO_MIME: dict[str, str] = {
    ".pdf": MIME_PDF,
    ".txt": MIME_PLAIN,
    ".text": MIME_PLAIN,
    ".md": MIME_MARKDOWN,
    ".markdown": MIME_MARKDOWN,
    ".doc": MIME_DOC,
    ".docx": MIME_DOCX,
    ".ppt": MIME_PPT,
    ".pptx": MIME_PPTX,
    ".xls": MIME_XLS,
    ".xlsx": MIME_XLSX,
}


def mime_from_name(name: str | None) -> str | None:
    raw = (name or "").strip().lower()
    for ext, mime in _EXT_TO_MIME.items():
        if raw.endswith(ext):
            return mime
    return None


def resolve_mime(mime_type: str | None, name: str | None = None) -> str | None:
    mime = (mime_type or "").strip()
    if mime and mime != "application/octet-stream":
        return mime
    return mime_from_name(name)


def needs_pdf_conversion(mime_type: str | None) -> bool:
    return (mime_type or "").strip() in CONVERT_TO_PDF_MIMES


def is_supported_mime(mime_type: str | None) -> bool:
    mime = (mime_type or "").strip()
    return mime in DIRECT_MIMES or mime in CONVERT_TO_PDF_MIMES


def require_supported_mime(mime_type: str | None, *, name: str | None = None) -> str:
    mime = resolve_mime(mime_type, name)
    if not mime or not is_supported_mime(mime):
        raise AppError(
            ErrorCategory.MICROSOFT_ONEDRIVE_FILE_TYPE_UNSUPPORTED,
            "This OneDrive file type is not supported.",
            details={"mime_type": mime or mime_type or None},
        )
    return mime


def suggested_filename(name: str | None, mime_type: str | None) -> str:
    base = (name or "onedrive-file").strip() or "onedrive-file"
    base = base.replace("/", "_").replace("\\", "_")
    mime = (mime_type or "").strip()
    lower = base.lower()
    if mime == MIME_PDF and not lower.endswith(".pdf"):
        return f"{base}.pdf"
    if mime == MIME_PLAIN and not (lower.endswith(".txt") or lower.endswith(".text")):
        return f"{base}.txt"
    if mime == MIME_MARKDOWN and not (
        lower.endswith(".md") or lower.endswith(".markdown")
    ):
        return f"{base}.md"
    return base
