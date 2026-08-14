"""Convert OpenRouter provider tokens into the Workspace AI token pool.

The Workspace has one ``ai_tokens`` allowance. Each OpenRouter family
(chat, embed, rerank, OCR, title) is billed as:

    billed = round(provider_tokens * family_multiplier)

Optional ``AI_TOKEN_MODEL_MULTIPLIERS`` JSON overrides the family rate for
an exact OpenRouter model id.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Any

from app.core.config import Settings
from app.usage.accounting import TokenUsage, chargeable_tokens

logger = logging.getLogger(__name__)


class OpenRouterFamily(StrEnum):
    CHAT = "chat"
    EMBED = "embed"
    RERANK = "rerank"
    OCR = "ocr"
    TITLE = "title"
    STT = "stt"


HISTORY_KIND_BY_FAMILY: dict[OpenRouterFamily, str] = {
    OpenRouterFamily.CHAT: "chat_tokens",
    OpenRouterFamily.EMBED: "embed_tokens",
    OpenRouterFamily.RERANK: "rerank_tokens",
    OpenRouterFamily.OCR: "ocr_tokens",
    OpenRouterFamily.TITLE: "title_tokens",
    OpenRouterFamily.STT: "stt_tokens",
}

AI_HISTORY_KINDS: frozenset[str] = frozenset(
    {*HISTORY_KIND_BY_FAMILY.values(), "ai_tokens"}
)

OPERATION_FAMILY: dict[str, OpenRouterFamily] = {
    "chat": OpenRouterFamily.CHAT,
    "generation": OpenRouterFamily.CHAT,
    "generation_attempt": OpenRouterFamily.CHAT,
    "general_expert": OpenRouterFamily.CHAT,
    "general_fallback": OpenRouterFamily.CHAT,
    "general_chat": OpenRouterFamily.CHAT,
    "embedding": OpenRouterFamily.EMBED,
    "embed_query": OpenRouterFamily.EMBED,
    "rerank": OpenRouterFamily.RERANK,
    "pdf_parse": OpenRouterFamily.OCR,
    "title": OpenRouterFamily.TITLE,
    "speech_to_text": OpenRouterFamily.STT,
}


def history_kind_for_operation(operation_type: str | None) -> str:
    family = OPERATION_FAMILY.get((operation_type or "").strip())
    if family is None:
        return HISTORY_KIND_BY_FAMILY[OpenRouterFamily.CHAT]
    return HISTORY_KIND_BY_FAMILY[family]


def parse_model_multipliers(raw: str | None) -> dict[str, float]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("ai_token_model_multipliers_invalid")
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in data.items():
        model = str(key).strip()
        if not model:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed < 0:
            continue
        out[model] = parsed
    return out


def family_multiplier(
    settings: Settings,
    family: OpenRouterFamily,
    model: str | None = None,
) -> float:
    model_id = (model or "").strip()
    overrides = parse_model_multipliers(settings.ai_token_model_multipliers)
    if model_id and model_id in overrides:
        return overrides[model_id]
    mapping = {
        OpenRouterFamily.CHAT: settings.ai_token_multiplier_chat,
        OpenRouterFamily.EMBED: settings.ai_token_multiplier_embed,
        OpenRouterFamily.RERANK: settings.ai_token_multiplier_rerank,
        OpenRouterFamily.OCR: settings.ai_token_multiplier_ocr,
        OpenRouterFamily.TITLE: settings.ai_token_multiplier_title,
        OpenRouterFamily.STT: settings.ai_token_multiplier_stt,
    }
    return max(0.0, float(mapping[family]))


def fallback_tokens_for(settings: Settings, family: OpenRouterFamily) -> int:
    if family == OpenRouterFamily.EMBED:
        return max(0, int(settings.ai_token_fallback_embed))
    if family == OpenRouterFamily.RERANK:
        return max(0, int(settings.ai_token_fallback_rerank))
    if family == OpenRouterFamily.OCR:
        return max(0, int(settings.ai_token_fallback_ocr_per_page))
    if family == OpenRouterFamily.TITLE:
        return max(0, int(settings.ai_token_fallback_title))
    if family == OpenRouterFamily.STT:
        return max(0, int(settings.ai_token_fallback_stt))
    return max(0, int(settings.effective_ai_usage_reservation_tokens))


def scale_usage(raw: TokenUsage, multiplier: float) -> TokenUsage:
    factor = max(0.0, float(multiplier))
    billed_total = max(0, round(raw.total_tokens * factor))
    if raw.prompt_tokens is None and raw.completion_tokens is None:
        return TokenUsage(
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=billed_total,
            source=raw.source,
        )
    if raw.total_tokens <= 0:
        prompt = 0 if raw.prompt_tokens is not None else None
        completion = 0 if raw.completion_tokens is not None else None
        return TokenUsage(prompt, completion, 0, raw.source)
    ratio = billed_total / raw.total_tokens
    prompt = (
        max(0, round(raw.prompt_tokens * ratio))
        if raw.prompt_tokens is not None
        else None
    )
    completion = (
        max(0, round(raw.completion_tokens * ratio))
        if raw.completion_tokens is not None
        else None
    )
    if prompt is not None and completion is not None and prompt + completion != billed_total:
        completion = max(0, billed_total - prompt)
        if prompt + completion != billed_total:
            prompt = billed_total - completion
    return TokenUsage(prompt, completion, billed_total, raw.source)


def billed_usage(
    settings: Settings,
    family: OpenRouterFamily,
    *,
    provider_usage: Any = None,
    model: str | None = None,
    fallback_tokens: int | None = None,
) -> tuple[TokenUsage, TokenUsage, float]:
    """Return ``(raw, billed, multiplier)`` for one OpenRouter call."""
    raw = chargeable_tokens(
        provider_usage=provider_usage,
        fallback_tokens=(
            fallback_tokens
            if fallback_tokens is not None
            else fallback_tokens_for(settings, family)
        ),
    )
    multiplier = family_multiplier(settings, family, model)
    return raw, scale_usage(raw, multiplier), multiplier


def settled_tokens_from_payload(
    settings: Settings,
    payload: dict[str, Any] | None,
    *,
    extra_billed: int = 0,
) -> int:
    data = payload or {}
    extra = max(0, int(data.get("billed_extra_tokens") or extra_billed or 0))
    chat_billed = data.get("billed_chat_tokens")
    if chat_billed is not None:
        try:
            return max(0, int(chat_billed)) + extra
        except (TypeError, ValueError):
            pass
    _raw, billed, _mult = billed_usage(
        settings,
        OpenRouterFamily.CHAT,
        provider_usage=data.get("usage"),
        model=data.get("model") if isinstance(data.get("model"), str) else None,
        fallback_tokens=settings.effective_ai_usage_reservation_tokens,
    )
    return billed.total_tokens + extra
