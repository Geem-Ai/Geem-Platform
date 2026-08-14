"""Transcribe chat mic audio via OpenRouter and bill STT immediately."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.chat_transcription.validation import inspect_chat_audio
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.openrouter.transcription import OpenRouterTranscriptionProvider
from app.usage.accounting import parse_provider_usage
from app.usage.openrouter_billing import record_openrouter_event
from app.usage.weights import OpenRouterFamily
from app.workspaces.models import Workspace


@dataclass(frozen=True, slots=True)
class ChatTranscribeResult:
    text: str
    duration_seconds: float | None


class ChatTranscriptionService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        provider: OpenRouterTranscriptionProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.provider = provider or OpenRouterTranscriptionProvider(settings=settings)

    def transcribe(
        self,
        *,
        workspace: Workspace,
        actor: User,
        file_bytes: bytes,
        filename: str,
        declared_mime_type: str | None = None,
        language: str | None = None,
    ) -> ChatTranscribeResult:
        inspection = inspect_chat_audio(
            file_bytes,
            filename,
            settings=self.settings,
            declared_mime_type=declared_mime_type,
        )
        result = self.provider.transcribe(
            file_bytes,
            audio_format=inspection.audio_format,
            language=language,
        )
        if not (result.text or "").strip():
            raise AppError(
                ErrorCategory.GENERATION_FAILED,
                "Speech transcription returned empty text",
                details={"request_id": result.request_id},
            )

        fallback = self._fallback_tokens(result.duration_seconds, result.usage)
        # Fail closed: quota/credit errors propagate; no transcript without charge.
        record_openrouter_event(
            self.db,
            self.settings,
            family=OpenRouterFamily.STT,
            operation_type="speech_to_text",
            provider_usage=result.usage,
            model=result.model,
            request_id=result.request_id or f"stt:{uuid.uuid4()}",
            workspace_id=workspace.id,
            user_id=actor.id,
            charge_now=True,
            fallback_tokens=fallback,
            extra_metadata={
                "duration_seconds": result.duration_seconds,
                "audio_format": inspection.audio_format,
                "byte_size": inspection.byte_size,
            },
        )
        self.db.commit()
        return ChatTranscribeResult(
            text=result.text.strip(),
            duration_seconds=result.duration_seconds,
        )

    def _fallback_tokens(
        self,
        duration_seconds: float | None,
        usage: dict | None,
    ) -> int:
        if parse_provider_usage(usage) is not None:
            # Provider tokens present — billed_usage will prefer them; fallback unused.
            return self.settings.ai_token_fallback_stt
        if duration_seconds is not None and duration_seconds >= 0:
            rate = max(0, int(self.settings.ai_token_stt_per_second))
            computed = max(0, int(math.ceil(float(duration_seconds) * rate)))
            if computed > 0:
                return computed
            # Zero/near-zero duration must not be free.
            return max(1, int(self.settings.ai_token_fallback_stt))
        return max(0, int(self.settings.ai_token_fallback_stt))
