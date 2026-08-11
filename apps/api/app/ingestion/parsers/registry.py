"""Format detection + parser lookup (Phase 3B).

Callers detect the Document format from ``(file_bytes, filename,
declared_mime_type)`` and receive a ``DocumentFormatDescriptor`` carrying
the canonical MIME type, the format name persisted on the ``Document`` row
via ``document.mime_type``, and the parser to invoke.

Detection rules:

* ``application/pdf`` — declared MIME is ``application/pdf`` OR filename ends
  in ``.pdf`` OR bytes start with ``%PDF``.
* ``text/markdown`` — filename ends in ``.md`` / ``.markdown`` OR declared
  MIME is ``text/markdown`` / ``text/x-markdown``.
* ``text/plain`` — filename ends in ``.txt`` OR declared MIME starts with
  ``text/``.
* Everything else → ``UNSUPPORTED_DOCUMENT_TYPE``.

We prefer content sniffing (magic bytes) over declared MIME when the two
disagree so a mislabelled upload cannot slip past validation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.errors import AppError, ErrorCategory
from app.ingestion.parsers.base import DocumentContentParser
from app.ingestion.parsers.markdown_parser import MarkdownParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.text_parser import TextParser


class DocumentFormat(str, enum.Enum):
    PDF = "pdf"
    TEXT = "text"
    MARKDOWN = "markdown"


@dataclass(frozen=True, slots=True)
class DocumentFormatDescriptor:
    format: DocumentFormat
    mime_type: str
    parser: DocumentContentParser


_MARKDOWN_MIME_ALIASES = frozenset({"text/markdown", "text/x-markdown"})
_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown", ".mdown", ".mkd"})
_TEXT_EXTENSIONS = frozenset({".txt", ".text"})


def _extension(filename: str) -> str:
    return PurePosixPath((filename or "").lower()).suffix


def _looks_like_pdf(file_bytes: bytes) -> bool:
    return file_bytes[:5].startswith(b"%PDF")


def detect_document_format(
    file_bytes: bytes,
    filename: str,
    declared_mime_type: str | None = None,
) -> DocumentFormatDescriptor:
    """Resolve a canonical format for an upload; raise for unsupported types."""
    declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()
    ext = _extension(filename)

    if _looks_like_pdf(file_bytes) or declared == "application/pdf" or ext == ".pdf":
        return DocumentFormatDescriptor(
            format=DocumentFormat.PDF,
            mime_type="application/pdf",
            parser=PdfParser(),
        )

    if ext in _MARKDOWN_EXTENSIONS or declared in _MARKDOWN_MIME_ALIASES:
        return DocumentFormatDescriptor(
            format=DocumentFormat.MARKDOWN,
            mime_type="text/markdown",
            parser=MarkdownParser(),
        )

    if ext in _TEXT_EXTENSIONS or declared == "text/plain" or (
        declared.startswith("text/") and declared not in _MARKDOWN_MIME_ALIASES
    ):
        return DocumentFormatDescriptor(
            format=DocumentFormat.TEXT,
            mime_type="text/plain",
            parser=TextParser(),
        )

    raise AppError(
        ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
        "Unsupported document type. Allowed: PDF, plain text, Markdown.",
        details={"declared_mime_type": declared_mime_type, "filename": filename},
    )


def get_parser_for_format(format_or_mime: str) -> DocumentContentParser:
    """Return a parser instance for a stored ``Document.mime_type`` value.

    Accepts either the canonical MIME (``text/plain``) or the short format
    name (``pdf``/``text``/``markdown``) so pipeline code can look up parsers
    from either representation.
    """
    normalized = (format_or_mime or "").split(";", 1)[0].strip().lower()
    if normalized in {DocumentFormat.PDF.value, "application/pdf"}:
        return PdfParser()
    if normalized in {DocumentFormat.MARKDOWN.value, "text/markdown", "text/x-markdown"}:
        return MarkdownParser()
    if normalized in {DocumentFormat.TEXT.value, "text/plain"} or normalized.startswith("text/"):
        return TextParser()
    raise AppError(
        ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
        f"No parser registered for format '{format_or_mime}'.",
    )


def resolve_parser(
    file_bytes: bytes,
    filename: str,
    declared_mime_type: str | None = None,
) -> DocumentFormatDescriptor:
    """Alias for :func:`detect_document_format` — legacy name."""
    return detect_document_format(file_bytes, filename, declared_mime_type)
