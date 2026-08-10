from __future__ import annotations

import io

from pypdf import PdfWriter

from app.ingestion.pdf_utils import split_page, validate_pdf_bytes


def _make_pdf(pages: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_validate_and_page_count():
    data = _make_pdf(3)
    info = validate_pdf_bytes(data, max_bytes=10_000_000, max_pages=100)
    assert info.page_count == 3


def test_split_page_is_one_based():
    data = _make_pdf(2)
    p1 = split_page(data, 1)
    p2 = split_page(data, 2)
    assert p1.startswith(b"%PDF")
    assert p2.startswith(b"%PDF")
    assert validate_pdf_bytes(p1, 10_000_000, 10).page_count == 1
    assert validate_pdf_bytes(p2, 10_000_000, 10).page_count == 1


def test_reject_non_pdf():
    import pytest
    from app.core.errors import AppError

    with pytest.raises(AppError):
        validate_pdf_bytes(b"not a pdf", 1000, 10)
