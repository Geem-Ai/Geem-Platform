"""PDF parser sentinel — defers to the OpenRouter OCR branch.

The Arabic-first OCR path in ``IngestionPipeline._ocr_pages`` remains the
single source of truth for PDF content. This parser exists so the format
registry can uniformly describe every Document format, but at pipeline
runtime it returns ``needs_ocr=True`` and the pipeline branches accordingly.
"""

from __future__ import annotations

from app.ingestion.parsers.base import ParsedDocument


class PdfParser:
    """Marker parser for ``application/pdf`` — keeps existing OCR pipeline."""

    mime_type = "application/pdf"
    format_name = "pdf"

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        return ParsedDocument(
            pages=(),
            page_count=0,
            mime_type=self.mime_type,
            needs_ocr=True,
        )
