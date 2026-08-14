"""OpenRouter speech-to-text (``/audio/transcriptions``)."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.openrouter.client import OpenRouterClient

logger = logging.getLogger(__name__)

_AUDIO_FORMATS = frozenset({"webm", "ogg", "wav", "mp3", "m4a", "flac", "aac"})


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    model: str | None
    request_id: str | None
    usage: dict[str, Any] | None
    duration_seconds: float | None


def parse_duration_seconds(usage: Any, body: dict[str, Any] | None = None) -> float | None:
    """Extract audio duration from OpenRouter/OpenAI-style STT payloads."""
    if isinstance(body, dict):
        for key in ("duration", "duration_seconds"):
            raw = body.get(key)
            if isinstance(raw, (int, float)) and raw >= 0:
                return float(raw)
    if not isinstance(usage, dict):
        return None
    for key in ("duration", "duration_seconds", "seconds"):
        raw = usage.get(key)
        if isinstance(raw, (int, float)) and raw >= 0:
            return float(raw)
    # OpenRouter duration-priced usage: {"type": "duration", "seconds": 1.2}
    if str(usage.get("type") or "").lower() == "duration":
        raw = usage.get("seconds")
        if isinstance(raw, (int, float)) and raw >= 0:
            return float(raw)
    return None


def normalize_audio_format(fmt: str | None) -> str:
    cleaned = (fmt or "").strip().lower().lstrip(".")
    if cleaned == "mpeg":
        cleaned = "mp3"
    if cleaned not in _AUDIO_FORMATS:
        raise AppError(
            ErrorCategory.UNSUPPORTED_AUDIO_TYPE,
            "Unsupported audio format. Allowed: webm, ogg, wav, mp3, m4a.",
            details={"format": fmt},
        )
    return cleaned


class OpenRouterTranscriptionProvider:
    def __init__(
        self,
        client: OpenRouterClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(self.settings)
        self.last_meta: dict[str, Any] = {}

    def transcribe(
        self,
        audio_bytes: bytes,
        *,
        audio_format: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        if not audio_bytes:
            raise AppError(ErrorCategory.INVALID_DOCUMENT, "Empty audio uploads are not allowed.")

        fmt = normalize_audio_format(audio_format)
        model = (self.settings.openrouter_stt_model or "").strip() or "google/chirp-3"
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        payload: dict[str, Any] = {
            "model": model,
            "input_audio": {"data": b64, "format": fmt},
        }
        lang = (language or "").strip().lower()
        if lang:
            # OpenRouter expects ISO-639-1; our UI uses en/ar.
            payload["language"] = lang[:2]

        body, meta, status = self.client.request(
            "POST",
            "/audio/transcriptions",
            json_body=payload,
            timeout=120.0,
        )
        self.last_meta = dict(meta or {})
        if status >= 400 or not isinstance(body, dict):
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Speech transcription failed",
                details={
                    "status": status,
                    "request_id": meta.get("request_id") if isinstance(meta, dict) else None,
                },
                retryable=status in {408, 429, 500, 502, 503, 504, 529},
            )

        text = body.get("text")
        if not isinstance(text, str):
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Speech transcription returned no text",
                details={"request_id": meta.get("request_id") if isinstance(meta, dict) else None},
            )

        usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
        if usage is None and isinstance(meta, dict) and isinstance(meta.get("usage"), dict):
            usage = meta["usage"]
        duration = parse_duration_seconds(usage, body)
        resolved_model = body.get("model") if isinstance(body.get("model"), str) else model
        request_id = meta.get("request_id") if isinstance(meta, dict) else None
        if isinstance(body.get("id"), str):
            self.last_meta["openrouter_id"] = body["id"]
        self.last_meta["model"] = resolved_model
        self.last_meta["usage"] = usage
        self.last_meta["duration_seconds"] = duration

        logger.info(
            "openrouter_transcription",
            extra={
                "request_id": request_id,
                "model": resolved_model,
                "duration_seconds": duration,
                "text_chars": len(text),
            },
        )
        return TranscriptionResult(
            text=text.strip(),
            model=resolved_model,
            request_id=request_id if isinstance(request_id, str) else None,
            usage=usage,
            duration_seconds=duration,
        )
