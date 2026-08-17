"""Unit tests for chat attachment validation (security-focused)."""

from __future__ import annotations

import pytest

from app.chat_attachments.validation import (
    inspect_chat_attachment,
    sanitize_attachment_filename,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


@pytest.fixture
def settings() -> Settings:
    return Settings(chat_attachment_max_mb=5)


def test_sanitize_strips_path_components() -> None:
    assert sanitize_attachment_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert "\x00" not in sanitize_attachment_filename("evil\x00name.txt")


def test_rejects_oversized_upload(settings: Settings) -> None:
    data = b"x" * (settings.chat_attachment_max_bytes + 1)
    with pytest.raises(AppError) as exc:
        inspect_chat_attachment(data, "big.txt", settings=settings)
    assert exc.value.category == ErrorCategory.UPLOAD_TOO_LARGE


def test_rejects_empty_upload(settings: Settings) -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_attachment(b"", "empty.txt", settings=settings)
    assert exc.value.category == ErrorCategory.INVALID_DOCUMENT


def test_rejects_pdf_extension_without_magic(settings: Settings) -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_attachment(b"not a pdf", "spoof.pdf", settings=settings)
    assert exc.value.category == ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE


def test_rejects_disallowed_extension(settings: Settings) -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_attachment(b"MZ", "malware.exe", settings=settings)
    assert exc.value.category == ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE


def test_accepts_utf8_text(settings: Settings) -> None:
    inspection = inspect_chat_attachment(
        "مرحبا Geem".encode("utf-8"),
        "note.txt",
        settings=settings,
        declared_mime_type="application/octet-stream",
    )
    assert inspection.mime_type == "text/plain"
    assert inspection.extension == "txt"
    assert len(inspection.sha256) == 64


def test_accepts_png_image(settings: Settings) -> None:
    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    inspection = inspect_chat_attachment(png, "dot.png", settings=settings)
    assert inspection.mime_type == "image/png"
    assert inspection.extension == "png"


def test_rejects_png_extension_without_magic(settings: Settings) -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_attachment(b"not-a-png", "spoof.png", settings=settings)
    assert exc.value.category == ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE


def test_rejects_nul_in_text(settings: Settings) -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_attachment(b"hello\x00world", "note.txt", settings=settings)
    assert exc.value.category == ErrorCategory.UNSUPPORTED_DOCUMENT_TYPE
