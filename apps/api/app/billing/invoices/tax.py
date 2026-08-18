"""VAT split for KSA simplified tax invoices. Catalog amounts are VAT-inclusive."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.billing.money import MONEY_QUANTUM, parse_decimal_money
from app.core.errors import AppError, ErrorCategory


def parse_vat_rate(raw: str | Decimal | float) -> Decimal:
    try:
        rate = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except Exception as exc:
        raise AppError(ErrorCategory.VALIDATION, "Invalid VAT rate.") from exc
    if rate < 0 or rate >= 1:
        raise AppError(ErrorCategory.VALIDATION, "VAT rate must be between 0 and 1.")
    return rate


def split_vat(
    *,
    amount: Decimal | str,
    rate: Decimal,
    prices_include_vat: bool = True,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(taxable, vat, total_including_vat)`` at 2 decimal places."""
    total = parse_decimal_money(amount)
    if prices_include_vat:
        if rate == 0:
            zero = Decimal("0.00")
            return total, zero, total
        taxable = (total / (Decimal(1) + rate)).quantize(
            MONEY_QUANTUM, rounding=ROUND_HALF_UP
        )
        vat = (total - taxable).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        return taxable, vat, total
    vat = (total * rate).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return total, vat, (total + vat).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def format_sar(value: Decimal | str) -> str:
    return f"{parse_decimal_money(value):.2f}"
