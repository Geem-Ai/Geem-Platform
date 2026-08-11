"""Multi-format Document parsers (Phase 3B).

Every Expert-linkable Document must yield the same downstream structure —
a list of ``ParsedDocumentPage`` objects — regardless of whether the source
is a PDF (OCR'd via OpenRouter) or a plain text / Markdown file. The
``registry`` module is the single place callers look up the right parser
by MIME type + filename extension; individual format modules keep the
per-format quirks (Markdown HTML stripping, TXT binary detection, PDF
staying on the existing OCR path).
"""

from __future__ import annotations

from app.ingestion.parsers.base import (
    DocumentContentParser,
    ParsedDocument,
    ParsedDocumentPage,
)
from app.ingestion.parsers.markdown_parser import MarkdownParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.registry import (
    DocumentFormat,
    DocumentFormatDescriptor,
    detect_document_format,
    get_parser_for_format,
    resolve_parser,
)
from app.ingestion.parsers.text_parser import TextParser

__all__ = [
    "DocumentContentParser",
    "ParsedDocument",
    "ParsedDocumentPage",
    "MarkdownParser",
    "PdfParser",
    "TextParser",
    "DocumentFormat",
    "DocumentFormatDescriptor",
    "detect_document_format",
    "get_parser_for_format",
    "resolve_parser",
]
