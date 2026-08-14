"""Validation for chat voice transcription uploads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

_ALLOWED_EXTENSIONS = frozenset({".webm", ".ogg", ".wav", ".mp3", ".m4a"})
_EXT_TO_FORMAT = {
    ".webm": "webm",
    ".ogg": "ogg",
    ".wav": "wav",
    ".mp3": "mp3",
    ".m4a": "m4a",
}
_MIME_TO_FORMAT = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
}
_FILENAME_SAFE = re.compile(r"[^\w.\-()\u0600-\u06FF ]+")


@dataclass(frozen=True, slots=True)
class ChatAudioInspection:
    safe_name: str
    audio_format: str
    mime_type: str
    byte_size: int


def sanitize_audio_filename(name: str) -> str:
    base = PurePosixPath((name or "").replace("\x00", "")).name
    base = _FILENAME_SAFE.sub("_", base).strip().strip(".")
    return base[:200] or "recording.webm"


def inspect_chat_audio(
    file_bytes: bytes,
    filename: str,
    *,
    settings: Settings,
    declared_mime_type: str | None = None,
) -> ChatAudioInspection:
    max_bytes = settings.chat_transcribe_max_bytes
    size = len(file_bytes)
    if size == 0:
        raise AppError(ErrorCategory.INVALID_DOCUMENT, "Empty audio uploads are not allowed.")
    if size > max_bytes:
        raise AppError(
            ErrorCategory.UPLOAD_TOO_LARGE,
            f"Upload exceeds maximum size of {max_bytes} bytes",
            details={"max_bytes": max_bytes, "byte_size": size},
        )

    safe_name = sanitize_audio_filename(filename)
    ext = PurePosixPath(safe_name).suffix.lower()
    declared = (declared_mime_type or "").split(";", 1)[0].strip().lower()

    audio_format: str | None = None
    if ext in _ALLOWED_EXTENSIONS:
        audio_format = _EXT_TO_FORMAT[ext]
    elif declared in _MIME_TO_FORMAT:
        audio_format = _MIME_TO_FORMAT[declared]
        # Ensure filename has a matching extension for downstream tooling.
        if not ext:
            safe_name = f"{safe_name}.{audio_format}"

    if audio_format is None:
        raise AppError(
            ErrorCategory.UNSUPPORTED_AUDIO_TYPE,
            "Unsupported audio format. Allowed: webm, ogg, wav, mp3, m4a.",
            details={"filename": safe_name, "declared_mime_type": declared_mime_type},
        )

    mime = declared if declared.startswith("audio/") else f"audio/{audio_format}"
    return ChatAudioInspection(
        safe_name=safe_name,
        audio_format=audio_format,
        mime_type=mime,
        byte_size=size,
    )
