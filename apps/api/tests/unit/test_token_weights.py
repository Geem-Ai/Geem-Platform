from __future__ import annotations

from app.core.config import Settings
from app.usage.weights import (
    OpenRouterFamily,
    billed_usage,
    family_multiplier,
    history_kind_for_operation,
    settled_tokens_from_payload,
)


def test_family_multiplier_defaults_ocr_triple() -> None:
    settings = Settings(ai_token_multiplier_chat=1.0, ai_token_multiplier_ocr=3.0)
    assert family_multiplier(settings, OpenRouterFamily.CHAT) == 1.0
    assert family_multiplier(settings, OpenRouterFamily.OCR) == 3.0


def test_model_json_override_wins_over_family() -> None:
    settings = Settings(
        ai_token_multiplier_ocr=3.0,
        ai_token_model_multipliers='{"openai/gpt-5.6-luna": 5}',
    )
    assert family_multiplier(settings, OpenRouterFamily.OCR, "openai/gpt-5.6-luna") == 5.0
    assert family_multiplier(settings, OpenRouterFamily.OCR, "other/model") == 3.0


def test_billed_usage_scales_prompt_and_completion() -> None:
    settings = Settings(ai_token_multiplier_ocr=3.0)
    raw, billed, multiplier = billed_usage(
        settings,
        OpenRouterFamily.OCR,
        provider_usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        model="openai/gpt-5.6-luna",
    )
    assert multiplier == 3.0
    assert raw.total_tokens == 15
    assert billed.total_tokens == 45
    assert billed.prompt_tokens == 30
    assert billed.completion_tokens == 15


def test_history_kind_for_operation() -> None:
    assert history_kind_for_operation("generation") == "chat_tokens"
    assert history_kind_for_operation("embed_query") == "embed_tokens"
    assert history_kind_for_operation("rerank") == "rerank_tokens"
    assert history_kind_for_operation("pdf_parse") == "ocr_tokens"
    assert history_kind_for_operation("title") == "title_tokens"
    assert history_kind_for_operation("speech_to_text") == "stt_tokens"


def test_settled_tokens_prefers_billed_fields() -> None:
    settings = Settings()
    total = settled_tokens_from_payload(
        settings,
        {
            "usage": {"total_tokens": 10},
            "billed_chat_tokens": 12,
            "billed_extra_tokens": 8,
        },
    )
    assert total == 20


def test_title_fallback_reads_settings() -> None:
    from app.usage.weights import fallback_tokens_for

    settings = Settings(ai_token_fallback_title=80)
    assert fallback_tokens_for(settings, OpenRouterFamily.TITLE) == 80


def test_stt_fallback_reads_settings() -> None:
    from app.usage.weights import fallback_tokens_for

    settings = Settings(ai_token_fallback_stt=777)
    assert fallback_tokens_for(settings, OpenRouterFamily.STT) == 777
    assert family_multiplier(Settings(ai_token_multiplier_stt=2.5), OpenRouterFamily.STT) == 2.5


def test_settled_tokens_weights_chat_when_billed_missing() -> None:
    settings = Settings(ai_token_multiplier_chat=2.0)
    total = settled_tokens_from_payload(
        settings,
        {"usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10}},
        extra_billed=3,
    )
    assert total == 23
