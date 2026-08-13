from __future__ import annotations

from app.usage.accounting import (
    accumulate_result_usage,
    chargeable_tokens,
    merge_token_usage,
    parse_provider_usage,
)


def test_parse_provider_usage_openai_shape() -> None:
    parsed = parse_provider_usage(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    )
    assert parsed is not None
    assert parsed.total_tokens == 15
    assert parsed.prompt_tokens == 10
    assert parsed.completion_tokens == 5
    assert parsed.source == "provider"


def test_parse_provider_usage_sums_when_total_missing() -> None:
    parsed = parse_provider_usage({"prompt_tokens": 8, "completion_tokens": 2})
    assert parsed is not None
    assert parsed.total_tokens == 10


def test_parse_provider_usage_rejects_garbage() -> None:
    assert parse_provider_usage(None) is None
    assert parse_provider_usage("nope") is None
    assert parse_provider_usage({"total_tokens": -1}) is None


def test_chargeable_tokens_prefers_provider_over_fallback() -> None:
    usage = chargeable_tokens(
        provider_usage={"total_tokens": 3},
        fallback_tokens=999,
    )
    assert usage.total_tokens == 3
    assert usage.source == "provider"


def test_chargeable_tokens_fallback_without_tokenizer() -> None:
    usage = chargeable_tokens(provider_usage=None, fallback_tokens=40)
    assert usage.total_tokens == 40
    assert usage.source == "fallback"
    assert usage.prompt_tokens is None


def test_accumulate_result_usage_sums_retry_and_fallback() -> None:
    target: dict = {}
    accumulate_result_usage(
        target,
        {"_meta": {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}},
    )
    accumulate_result_usage(
        target,
        {"_meta": {"usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}}},
    )
    accumulate_result_usage(target, {"_meta": {"usage": None}})
    assert target["usage"]["total_tokens"] == 25
    assert target["usage"]["prompt_tokens"] == 18
    assert target["usage"]["completion_tokens"] == 7


def test_merge_token_usage_from_empty() -> None:
    parsed = parse_provider_usage({"total_tokens": 4})
    assert parsed is not None
    merged = merge_token_usage(None, parsed)
    assert merged["total_tokens"] == 4
