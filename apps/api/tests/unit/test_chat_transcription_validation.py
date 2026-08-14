"""Unit tests for chat voice transcription validation."""

from __future__ import annotations

import pytest

from app.chat_transcription.validation import inspect_chat_audio
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def _settings(**kwargs: object) -> Settings:
    return Settings(chat_transcribe_max_mb=1, **kwargs)  # type: ignore[arg-type]


def test_inspect_accepts_webm() -> None:
    data = b"\x1a\x45\xdf\xa3fake-webm"
    result = inspect_chat_audio(
        data,
        "clip.webm",
        settings=_settings(),
        declared_mime_type="audio/webm",
    )
    assert result.audio_format == "webm"
    assert result.byte_size == len(data)


def test_inspect_accepts_mime_when_extension_missing() -> None:
    data = b"ogg-bytes"
    result = inspect_chat_audio(
        data,
        "recording",
        settings=_settings(),
        declared_mime_type="audio/ogg;codecs=opus",
    )
    assert result.audio_format == "ogg"
    assert result.safe_name.endswith(".ogg")


def test_inspect_rejects_empty() -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_audio(b"", "a.webm", settings=_settings())
    assert exc.value.category == ErrorCategory.INVALID_DOCUMENT


def test_inspect_rejects_too_large() -> None:
    settings = Settings(chat_transcribe_max_mb=1)
    payload = b"x" * (settings.chat_transcribe_max_bytes + 1)
    with pytest.raises(AppError) as exc:
        inspect_chat_audio(payload, "a.webm", settings=settings)
    assert exc.value.category == ErrorCategory.UPLOAD_TOO_LARGE


def test_inspect_rejects_pdf() -> None:
    with pytest.raises(AppError) as exc:
        inspect_chat_audio(
            b"%PDF-1.4",
            "doc.pdf",
            settings=_settings(),
            declared_mime_type="application/pdf",
        )
    assert exc.value.category == ErrorCategory.UNSUPPORTED_AUDIO_TYPE
