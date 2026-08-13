"""SAR money helpers. Phase 6 is single-currency; do not invent FX logic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.core.errors import AppError, ErrorCategory

MONEY_QUANTUM = Decimal("0.01")
DEFAULT_CURRENCY = "SAR"


def parse_decimal_money(value: Decimal | int | float | str) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AppError(ErrorCategory.VALIDATION, "Invalid money amount.") from exc
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def quantize_money(value: Decimal | int | float | str) -> Decimal:
    quantized = parse_decimal_money(value)
    if quantized <= 0:
        raise AppError(ErrorCategory.VALIDATION, "Amount must be greater than zero.")
    return quantized


def money_equal(left: Decimal | int | float | str, right: Decimal | int | float | str) -> bool:
    return parse_decimal_money(left) == parse_decimal_money(right)


def normalize_currency(value: str | None, *, default: str = DEFAULT_CURRENCY) -> str:
    code = (value or default).strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise AppError(ErrorCategory.VALIDATION, "Currency must be a 3-letter code.")
    return code
