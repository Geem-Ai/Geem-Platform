"""Plain-text Document parser (Phase 3B).

Accepts UTF-8 (with optional BOM) text uploads. Rejects binary payloads
(null bytes, or a high ratio of non-printable/control bytes) so a mis-typed
PDF/image cannot bypass the PDF validator by claiming ``text/plain``.

Text files always produce a single ``ParsedDocumentPage`` — the chunker is
responsible for further token-based splitting.
"""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory
from app.ingestion.parsers.base import ParsedDocument, ParsedDocumentPage

# Any bytes below space that are not whitespace count as "control" for the
# binary-detection heuristic. NUL always wins on its own.
_ALLOWED_LOW_BYTES = frozenset({0x09, 0x0A, 0x0D})  # tab, LF, CR
_BINARY_RATIO_THRESHOLD = 0.30


def _looks_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True
    sample = data[:8192]
    if not sample:
        return False
    control = 0
    for byte in sample:
        if byte < 0x20 and byte not in _ALLOWED_LOW_BYTES:
            control += 1
        elif byte == 0x7F:
            control += 1
    return (control / len(sample)) > _BINARY_RATIO_THRESHOLD


def _decode_utf8(data: bytes) -> str:
    stripped = data
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = stripped[3:]
    try:
        return stripped.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AppError(
            ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
            "Text uploads must be UTF-8 encoded.",
        ) from exc


class TextParser:
    """Parse a plain-text UTF-8 upload into a single-page ``ParsedDocument``."""

    mime_type = "text/plain"
    format_name = "text"

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        if _looks_binary(file_bytes):
            raise AppError(
                ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE,
                "File appears to be binary; only UTF-8 text is supported.",
            )
        text = _decode_utf8(file_bytes)
        cleaned = text.strip()
        if not cleaned:
            raise AppError(
                ErrorCategory.EMPTY_PAGE,
                "Text upload contains no readable content.",
            )
        page = ParsedDocumentPage(
            page_number=1,
            raw_markdown=cleaned,
            plain_text=cleaned,
            metadata={"format": self.format_name, "source_filename": filename},
        )
        return ParsedDocument(
            pages=(page,),
            page_count=1,
            mime_type=self.mime_type,
            needs_ocr=False,
        )
