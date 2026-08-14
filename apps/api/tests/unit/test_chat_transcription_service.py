"""Unit tests for OpenRouter transcription helpers + chat STT service billing."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.chat_transcription.service import ChatTranscriptionService
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.openrouter.transcription import (
    TranscriptionResult,
    parse_duration_seconds,
)
from app.usage.weights import OpenRouterFamily, billed_usage, history_kind_for_operation


def test_parse_duration_from_usage_type() -> None:
    assert parse_duration_seconds({"type": "duration", "seconds": 1.5}) == 1.5
    assert parse_duration_seconds({"duration": 3}) == 3.0
    assert parse_duration_seconds(None, {"duration": 2.25}) == 2.25
    assert parse_duration_seconds({}) is None


def test_stt_history_kind_and_multiplier() -> None:
    settings = Settings(ai_token_multiplier_stt=2.0)
    assert history_kind_for_operation("speech_to_text") == "stt_tokens"
    raw, billed, mult = billed_usage(
        settings,
        OpenRouterFamily.STT,
        provider_usage={"total_tokens": 100},
    )
    assert mult == 2.0
    assert raw.total_tokens == 100
    assert billed.total_tokens == 200


def test_stt_duration_fallback_via_service(db) -> None:
    settings = Settings(
        ai_token_multiplier_stt=2.0,
        ai_token_stt_per_second=50,
        ai_token_fallback_stt=500,
    )

    workspace = MagicMock()
    workspace.id = None  # avoid FK on usage_events.workspace_id
    workspace.is_tenant = False
    actor = MagicMock()
    actor.id = None

    provider = MagicMock()
    provider.transcribe.return_value = TranscriptionResult(
        text="مرحبا",
        model="openai/whisper-1",
        request_id="req-stt-1",
        usage={"type": "duration", "seconds": 2},
        duration_seconds=2.0,
    )

    svc = ChatTranscriptionService(db, settings, provider=provider)
    result = svc.transcribe(
        workspace=workspace,
        actor=actor,
        file_bytes=b"fake-audio",
        filename="clip.webm",
        declared_mime_type="audio/webm",
        language="ar",
    )
    assert result.text == "مرحبا"
    assert result.duration_seconds == 2.0

    event = db.query(UsageEvent).filter(UsageEvent.request_id == "req-stt-1").one()
    assert event.operation_type == "speech_to_text"
    assert event.cost_metadata["family"] == "stt"
    # 2s * 50 = 100 raw → * 2.0 multiplier = 200 billed
    assert event.cost_metadata["billed_tokens"] == 200
    assert event.cost_metadata["token_source"] == "fallback"


def test_stt_zero_duration_is_not_free(db) -> None:
    settings = Settings(
        ai_token_multiplier_stt=2.0,
        ai_token_stt_per_second=50,
        ai_token_fallback_stt=500,
    )
    workspace = MagicMock()
    workspace.id = None
    workspace.is_tenant = False
    actor = MagicMock()
    actor.id = None

    provider = MagicMock()
    provider.transcribe.return_value = TranscriptionResult(
        text="hi",
        model="openai/whisper-1",
        request_id="req-stt-zero",
        usage={"type": "duration", "seconds": 0},
        duration_seconds=0.0,
    )

    svc = ChatTranscriptionService(db, settings, provider=provider)
    svc.transcribe(
        workspace=workspace,
        actor=actor,
        file_bytes=b"fake-audio",
        filename="clip.webm",
        declared_mime_type="audio/webm",
    )
    event = db.query(UsageEvent).filter(UsageEvent.request_id == "req-stt-zero").one()
    # fallback 500 raw * 2.0 multiplier
    assert event.cost_metadata["billed_tokens"] == 1000
    assert event.cost_metadata["token_source"] == "fallback"


def test_stt_quota_failure_does_not_return_text(db, monkeypatch) -> None:
    settings = Settings()
    workspace = MagicMock()
    workspace.id = uuid.uuid4()
    workspace.is_tenant = True
    actor = MagicMock()
    actor.id = uuid.uuid4()

    provider = MagicMock()
    provider.transcribe.return_value = TranscriptionResult(
        text="secret transcript",
        model="openai/whisper-1",
        request_id="req-stt-quota",
        usage={"total_tokens": 10},
        duration_seconds=None,
    )

    def _boom(*_a: Any, **_k: Any) -> int:
        raise AppError(ErrorCategory.QUOTA_EXCEEDED, "AI token quota exceeded")

    monkeypatch.setattr(
        "app.chat_transcription.service.record_openrouter_event",
        _boom,
    )

    svc = ChatTranscriptionService(db, settings, provider=provider)
    with pytest.raises(AppError) as exc:
        svc.transcribe(
            workspace=workspace,
            actor=actor,
            file_bytes=b"fake-audio",
            filename="clip.webm",
            declared_mime_type="audio/webm",
        )
    assert exc.value.category == ErrorCategory.QUOTA_EXCEEDED
