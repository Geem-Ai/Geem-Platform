"""Phase 5A — entitlement value parsing (no plan-name branching)."""

from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey, EntitlementValueType
from app.entitlements.values import (
    EntitlementValue,
    parse_boolean_entitlement,
    parse_integer_entitlement,
    serialize_entitlement_value,
)


def test_parse_integer_valid() -> None:
    assert parse_integer_entitlement(EntitlementKey.EXPERTS_LIMIT.value, "0") == 0
    assert parse_integer_entitlement(EntitlementKey.EXPERTS_LIMIT.value, "42") == 42
    assert parse_integer_entitlement(EntitlementKey.STORAGE_BYTES.value, "10737418240") == 10737418240
    assert parse_integer_entitlement("custom", "-3") == -3


def test_parse_integer_rejects_invalid() -> None:
    for raw in ("", "1.5", "true", "01", "1e3", "  ", "+", "--1", "1_000"):
        with pytest.raises(AppError) as exc:
            parse_integer_entitlement(EntitlementKey.AI_TOKENS_DAILY.value, raw)
        assert exc.value.category == ErrorCategory.ENTITLEMENT_INVALID


def test_parse_boolean() -> None:
    assert parse_boolean_entitlement("flag", "true") is True
    assert parse_boolean_entitlement("flag", "TRUE") is True
    assert parse_boolean_entitlement("flag", "1") is True
    assert parse_boolean_entitlement("flag", "yes") is True
    assert parse_boolean_entitlement("flag", "false") is False
    assert parse_boolean_entitlement("flag", "0") is False
    assert parse_boolean_entitlement("flag", "no") is False
    with pytest.raises(AppError) as exc:
        parse_boolean_entitlement("flag", "maybe")
    assert exc.value.category == ErrorCategory.ENTITLEMENT_INVALID


def test_typed_accessors_mismatch() -> None:
    integer = EntitlementValue(
        key=EntitlementKey.EXPERTS_LIMIT.value,
        raw="5",
        value_type=EntitlementValueType.INTEGER,
    )
    assert integer.as_int() == 5
    assert integer.as_python() == 5
    with pytest.raises(AppError) as exc:
        integer.as_bool()
    assert exc.value.category == ErrorCategory.ENTITLEMENT_TYPE_MISMATCH


def test_serialize_roundtrip() -> None:
    assert serialize_entitlement_value(10, EntitlementValueType.INTEGER) == "10"
    assert serialize_entitlement_value(True, EntitlementValueType.BOOLEAN) == "true"
    assert serialize_entitlement_value("gpt", EntitlementValueType.STRING) == "gpt"
    with pytest.raises(AppError):
        serialize_entitlement_value(True, EntitlementValueType.INTEGER)
    with pytest.raises(AppError):
        serialize_entitlement_value(1, EntitlementValueType.BOOLEAN)


def test_canonical_keys_are_stable() -> None:
    assert EntitlementKey.AI_TOKENS_DAILY.value == "ai_tokens_daily"
    assert EntitlementKey.AI_TOKENS_WEEKLY.value == "ai_tokens_weekly"
    assert EntitlementKey.AI_TOKENS_MONTHLY.value == "ai_tokens_monthly"
    assert EntitlementKey.EXPERTS_LIMIT.value == "experts_limit"
    assert EntitlementKey.STORAGE_BYTES.value == "storage_bytes"
