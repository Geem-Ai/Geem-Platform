"""Typed entitlement value parsing.

Stored representation is always (value TEXT, value_type). Future boolean /
numeric / string entitlements share this parser without a schema redesign.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError, ErrorCategory
from app.entitlements.keys import EntitlementKey, EntitlementValueType


@dataclass(frozen=True, slots=True)
class EntitlementValue:
    key: str
    raw: str
    value_type: EntitlementValueType

    def as_python(self) -> int | bool | str:
        if self.value_type == EntitlementValueType.INTEGER:
            return self.as_int()
        if self.value_type == EntitlementValueType.BOOLEAN:
            return self.as_bool()
        return self.as_str()

    def as_int(self) -> int:
        if self.value_type != EntitlementValueType.INTEGER:
            raise AppError(
                ErrorCategory.ENTITLEMENT_TYPE_MISMATCH,
                f"Entitlement '{self.key}' is {self.value_type}, not integer.",
                details={"key": self.key, "value_type": self.value_type.value},
            )
        return parse_integer_entitlement(self.key, self.raw)

    def as_bool(self) -> bool:
        if self.value_type != EntitlementValueType.BOOLEAN:
            raise AppError(
                ErrorCategory.ENTITLEMENT_TYPE_MISMATCH,
                f"Entitlement '{self.key}' is {self.value_type}, not boolean.",
                details={"key": self.key, "value_type": self.value_type.value},
            )
        return parse_boolean_entitlement(self.key, self.raw)

    def as_str(self) -> str:
        return self.raw


def parse_integer_entitlement(key: str, raw: str) -> int:
    text = (raw or "").strip()
    if text.startswith("-"):
        digits = text[1:]
        negative = True
    else:
        digits = text
        negative = False
    if not digits.isdigit() or digits == "":
        raise AppError(
            ErrorCategory.ENTITLEMENT_INVALID,
            f"Entitlement '{key}' is not a valid integer.",
            details={"key": key, "value": raw},
        )
    # Reject leading zeros except a lone "0" (and "-0" → 0).
    if len(digits) > 1 and digits.startswith("0"):
        raise AppError(
            ErrorCategory.ENTITLEMENT_INVALID,
            f"Entitlement '{key}' is not a valid integer.",
            details={"key": key, "value": raw},
        )
    value = int(digits)
    return -value if negative else value


def parse_boolean_entitlement(key: str, raw: str) -> bool:
    text = (raw or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise AppError(
        ErrorCategory.ENTITLEMENT_INVALID,
        f"Entitlement '{key}' is not a valid boolean.",
        details={"key": key, "value": raw},
    )


def serialize_entitlement_value(value: Any, value_type: EntitlementValueType) -> str:
    if value_type == EntitlementValueType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError(
                ErrorCategory.ENTITLEMENT_INVALID,
                "Integer entitlement requires an int.",
            )
        return str(value)
    if value_type == EntitlementValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise AppError(
                ErrorCategory.ENTITLEMENT_INVALID,
                "Boolean entitlement requires a bool.",
            )
        return "true" if value else "false"
    if not isinstance(value, str):
        raise AppError(
            ErrorCategory.ENTITLEMENT_INVALID,
            "String entitlement requires a str.",
        )
    return value


def entitlement_value_from_row(
    *,
    key: str,
    raw: str,
    value_type: str,
) -> EntitlementValue:
    try:
        parsed_type = EntitlementValueType(value_type)
    except ValueError as exc:
        raise AppError(
            ErrorCategory.ENTITLEMENT_INVALID,
            f"Unknown entitlement value_type '{value_type}'.",
            details={"key": key, "value_type": value_type},
        ) from exc
    return EntitlementValue(key=key, raw=raw, value_type=parsed_type)


def require_known_key(key: str | EntitlementKey) -> str:
    if isinstance(key, EntitlementKey):
        return key.value
    return str(key)
