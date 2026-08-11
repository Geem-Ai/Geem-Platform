"""Markdown Document parser (Phase 3B).

Accepts UTF-8 Markdown. Because Markdown legally embeds HTML, we defensively
strip ``<script>`` / ``<style>`` blocks and never execute or render HTML —
the downstream RAG pipeline treats parsed text as opaque content, not as
markup. Everything else (headings, lists, emphasis) is preserved verbatim so
the chunker's Markdown-aware heuristics keep working.

Like ``TextParser`` this always yields a single ``ParsedDocumentPage``.
"""

from __future__ import annotations

import re

from app.core.errors import AppError, ErrorCategory
from app.ingestion.parsers.base import ParsedDocument, ParsedDocumentPage
from app.ingestion.parsers.text_parser import _decode_utf8, _looks_binary

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)


def _sanitize_markdown(text: str) -> str:
    cleaned = _SCRIPT_STYLE_RE.sub(" ", text)
    cleaned = _HTML_COMMENT_RE.sub(" ", cleaned)
    return cleaned


def _markdown_to_plain(text: str) -> str:
    plain = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    plain = re.sub(r"`[^`]*`", " ", plain)
    plain = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", plain)
    plain = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", plain)
    plain = re.sub(r"[#>*_~`]+", " ", plain)
    plain = re.sub(r"\s+", " ", plain)
    return plain.strip()


class MarkdownParser:
    """Parse a Markdown UTF-8 upload into a single-page ``ParsedDocument``."""

    mime_type = "text/markdown"
    format_name = "markdown"

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        if _looks_binary(file_bytes):
            raise AppError(
                ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
                "File appears to be binary; only UTF-8 Markdown is supported.",
            )
        text = _decode_utf8(file_bytes)
        sanitized = _sanitize_markdown(text).strip()
        if not sanitized:
            raise AppError(
                ErrorCategory.EMPTY_PAGE,
                "Markdown upload contains no readable content.",
            )
        page = ParsedDocumentPage(
            page_number=1,
            raw_markdown=sanitized,
            plain_text=_markdown_to_plain(sanitized),
            metadata={"format": self.format_name, "source_filename": filename},
        )
        return ParsedDocument(
            pages=(page,),
            page_count=1,
            mime_type=self.mime_type,
            needs_ocr=False,
        )
