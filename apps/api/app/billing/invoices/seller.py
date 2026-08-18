"""Seller identity for ZATCA simplified tax invoices."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

# KSA VAT registration numbers are 15 digits and start/end with 3.
_VAT_RE = re.compile(r"^3\d{13}3$")
_LOCAL_TEST_VAT = "399999999900003"


@dataclass(frozen=True)
class SellerProfile:
    name: str
    name_ar: str
    vat_number: str
    cr_number: str
    address: str
    address_ar: str
    sample: bool


def _clean(value: str | None) -> str:
    return (value or "").strip()


def seller_profile(settings: Settings) -> SellerProfile:
    name = _clean(settings.invoice_seller_name) or "Geem"
    name_ar = _clean(settings.invoice_seller_name_ar) or "جيم"
    vat = re.sub(r"\D", "", _clean(settings.invoice_vat_number))
    sample = False
    if not vat:
        if settings.is_local:
            vat = _LOCAL_TEST_VAT
            sample = True
        else:
            raise AppError(
                ErrorCategory.INVOICE_NOT_CONFIGURED,
                "Set INVOICE_VAT_NUMBER before issuing tax invoices.",
            )
    elif not _VAT_RE.fullmatch(vat):
        raise AppError(
            ErrorCategory.INVOICE_NOT_CONFIGURED,
            "INVOICE_VAT_NUMBER must be a 15-digit KSA VAT number starting and ending with 3.",
        )
    return SellerProfile(
        name=name,
        name_ar=name_ar,
        vat_number=vat,
        cr_number=_clean(settings.invoice_cr_number),
        address=_clean(settings.invoice_address),
        address_ar=_clean(settings.invoice_address_ar),
        sample=sample,
    )
