from __future__ import annotations

from starlette.responses import Response

from app.api.documents import content_disposition_inline


def test_content_disposition_inline_ascii():
    header = content_disposition_inline("report.pdf")
    assert 'filename="report.pdf"' in header
    assert "filename*=UTF-8''report.pdf" in header
    Response(content=b"%PDF", headers={"Content-Disposition": header})


def test_content_disposition_inline_arabic():
    header = content_disposition_inline("01 جيم.pdf")
    assert "filename=" in header
    assert "filename*=UTF-8''" in header
    assert "%D8%AC%D9%8A%D9%85" in header  # جيم
    # Must be encodable as latin-1 (Starlette requirement)
    Response(content=b"%PDF", media_type="application/pdf", headers={"Content-Disposition": header})
