"""Common interface + data shapes for Document content parsers (Phase 3B).

The pipeline treats every Document as a series of parsed pages that feed the
chunker/embedder unchanged. PDFs still go through OpenRouter OCR page-by-page
(handled by ``PdfParser`` yielding a sentinel so the pipeline runs its OCR
branch). Text-based formats — plain text and Markdown — produce a single
``ParsedDocumentPage`` and skip OCR entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ParsedDocumentPage:
    """One page of a parsed Document, ready for chunking/embedding."""

    page_number: int
    raw_markdown: str
    plain_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """A fully-parsed Document ready for the ingestion pipeline.

    ``needs_ocr=True`` is a sentinel returned by ``PdfParser`` to signal that
    the pipeline should keep using its existing per-page OCR branch. In that
    case ``pages`` is empty and ``page_count`` is authoritative (already
    populated on the ``Document`` row by the upload validator).
    """

    pages: tuple[ParsedDocumentPage, ...]
    page_count: int
    mime_type: str
    needs_ocr: bool = False


@runtime_checkable
class DocumentContentParser(Protocol):
    """Shape of every Document parser exposed to the ingestion pipeline.

    Implementations must be side-effect-free and safe to call synchronously.
    Failure modes (unsupported encoding, oversized file, binary payload) are
    surfaced by raising ``AppError`` with a stable ``ErrorCategory``.
    """

    mime_type: str
    format_name: str

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        """Return a fully-parsed Document (or a ``needs_ocr`` sentinel)."""
        ...
