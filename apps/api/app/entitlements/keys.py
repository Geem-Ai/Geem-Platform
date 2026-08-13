"""Canonical entitlement keys and value types.

Product limits MUST be resolved through these keys. Never branch on plan
code/name (no ``if plan.code == "pro"``).
"""

from __future__ import annotations

from enum import StrEnum


class EntitlementValueType(StrEnum):
    INTEGER = "integer"
    BOOLEAN = "boolean"
    STRING = "string"


class EntitlementKey(StrEnum):
    """Single source of truth for entitlement key strings."""

    AI_TOKENS_DAILY = "ai_tokens_daily"
    AI_TOKENS_WEEKLY = "ai_tokens_weekly"
    AI_TOKENS_MONTHLY = "ai_tokens_monthly"
    EXPERTS_LIMIT = "experts_limit"
    STORAGE_BYTES = "storage_bytes"


QUOTA_INTEGER_KEYS: frozenset[EntitlementKey] = frozenset(
    {
        EntitlementKey.AI_TOKENS_DAILY,
        EntitlementKey.AI_TOKENS_WEEKLY,
        EntitlementKey.AI_TOKENS_MONTHLY,
        EntitlementKey.EXPERTS_LIMIT,
        EntitlementKey.STORAGE_BYTES,
    }
)

# Display order: daily → weekly → monthly (not alphabetical; monthly < weekly lexicographically).
ENTITLEMENT_DISPLAY_ORDER: tuple[str, ...] = (
    EntitlementKey.AI_TOKENS_DAILY.value,
    EntitlementKey.AI_TOKENS_WEEKLY.value,
    EntitlementKey.AI_TOKENS_MONTHLY.value,
    EntitlementKey.EXPERTS_LIMIT.value,
    EntitlementKey.STORAGE_BYTES.value,
)


def entitlement_display_sort_key(key: str) -> tuple[int, str]:
    try:
        return (ENTITLEMENT_DISPLAY_ORDER.index(key), key)
    except ValueError:
        return (len(ENTITLEMENT_DISPLAY_ORDER), key)


def parse_entitlement_key(raw: str) -> EntitlementKey:
    try:
        return EntitlementKey(raw)
    except ValueError as exc:
        raise ValueError(f"Unknown entitlement key: {raw}") from exc
