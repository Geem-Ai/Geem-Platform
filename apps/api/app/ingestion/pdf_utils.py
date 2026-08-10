from __future__ import annotations

import io
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from app.core.errors import AppError, ErrorCategory

PDF_MAGIC = b"%PDF"


@dataclass
class PdfInfo:
    page_count: int
    encrypted: bool


def validate_pdf_bytes(data: bytes, max_bytes: int, max_pages: int) -> PdfInfo:
    if len(data) > max_bytes:
        raise AppError(
            ErrorCategory.INVALID_PDF,
            f"PDF exceeds maximum size of {max_bytes} bytes",
        )
    if not data.startswith(PDF_MAGIC):
        raise AppError(ErrorCategory.INVALID_PDF, "File is not a valid PDF (missing %PDF header)")

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except PdfReadError as exc:
        raise AppError(ErrorCategory.INVALID_PDF, f"Unable to read PDF: {exc}") from exc

    if reader.is_encrypted:
        # Try empty password; still reject for MVP if encrypted
        try:
            reader.decrypt("")
        except Exception:
            pass
        if reader.is_encrypted:
            raise AppError(ErrorCategory.ENCRYPTED_PDF, "Encrypted PDFs are not supported")

    page_count = len(reader.pages)
    if page_count <= 0:
        raise AppError(ErrorCategory.INVALID_PDF, "PDF has no pages")
    if page_count > max_pages:
        raise AppError(
            ErrorCategory.INVALID_PDF,
            f"PDF has {page_count} pages; maximum allowed is {max_pages}",
        )
    return PdfInfo(page_count=page_count, encrypted=False)


def split_page(pdf_bytes: bytes, page_number: int) -> bytes:
    """Extract a single 1-based page as a standalone PDF. No text extraction."""
    reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    if page_number < 1 or page_number > len(reader.pages):
        raise AppError(
            ErrorCategory.INVALID_PDF,
            f"Page {page_number} out of range (1..{len(reader.pages)})",
        )
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
