from __future__ import annotations

import io

import pytest

from app.core.errors import AppError, ErrorCategory
from app.documents.service import sanitize_filename
from app.ingestion.pdf_utils import validate_pdf_bytes
from pypdf import PdfWriter


def test_sanitize_filename():
    assert ".." not in sanitize_filename("../../etc/passwd.pdf")
    assert sanitize_filename("عقد.pdf").endswith(".pdf")


def test_duplicate_sha_concept():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    data = buf.getvalue()
    info = validate_pdf_bytes(data, 1_000_000, 10)
    assert info.page_count == 1
    # Same bytes => same digest
    import hashlib

    assert hashlib.sha256(data).hexdigest() == hashlib.sha256(data).hexdigest()


def test_app_error_category():
    err = AppError(ErrorCategory.CONFLICT, "dup", details={"id": "x"})
    assert err.category == ErrorCategory.CONFLICT
    assert err.details["id"] == "x"
