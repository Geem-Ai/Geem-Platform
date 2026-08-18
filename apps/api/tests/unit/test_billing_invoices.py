from __future__ import annotations

import base64
from decimal import Decimal

import pytest

from app.billing.invoices.pdf import render_simplified_tax_invoice
from app.billing.invoices.seller import seller_profile
from app.billing.invoices.tax import split_vat
from app.billing.invoices.zatca import zatca_qr_base64
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def _decode_tlv(payload: str) -> dict[int, str]:
    raw = base64.b64decode(payload)
    out: dict[int, str] = {}
    i = 0
    while i < len(raw):
        tag = raw[i]
        length = raw[i + 1]
        out[tag] = raw[i + 2 : i + 2 + length].decode("utf-8")
        i += 2 + length
    return out


def test_split_vat_inclusive_standard_ksa_rate() -> None:
    taxable, vat, total = split_vat(
        amount="25.00",
        rate=Decimal("0.15"),
        prices_include_vat=True,
    )
    assert total == Decimal("25.00")
    assert taxable == Decimal("21.74")
    assert vat == Decimal("3.26")
    assert taxable + vat == total


def test_split_vat_exclusive() -> None:
    taxable, vat, total = split_vat(
        amount="100.00",
        rate=Decimal("0.15"),
        prices_include_vat=False,
    )
    assert taxable == Decimal("100.00")
    assert vat == Decimal("15.00")
    assert total == Decimal("115.00")


def test_zatca_qr_tlv_tags() -> None:
    encoded = zatca_qr_base64(
        seller_name="جيم",
        vat_number="399999999900003",
        timestamp="2026-08-18T17:02:00+03:00",
        total_with_vat="25.00",
        vat_amount="3.26",
    )
    tags = _decode_tlv(encoded)
    assert tags[1] == "جيم"
    assert tags[2] == "399999999900003"
    assert tags[3] == "2026-08-18T17:02:00+03:00"
    assert tags[4] == "25.00"
    assert tags[5] == "3.26"


def test_local_seller_uses_sample_vat() -> None:
    profile = seller_profile(
        Settings(_env_file=None, app_env="test", invoice_vat_number="")
    )
    assert profile.sample is True
    assert profile.vat_number == "399999999900003"


def test_production_seller_requires_vat() -> None:
    with pytest.raises(AppError) as exc:
        seller_profile(Settings(_env_file=None, app_env="production", invoice_vat_number=""))
    assert exc.value.category == ErrorCategory.INVOICE_NOT_CONFIGURED


def test_render_simplified_invoice_pdf_contains_required_fields() -> None:
    pdf = render_simplified_tax_invoice(
        {
            "invoice_number": "GEEM-000001",
            "invoice_type": "simplified_tax_invoice",
            "currency": "SAR",
            "issued_at": "2026-08-18T17:02:00+03:00",
            "vat_rate": "0.15",
            "taxable_amount": "21.74",
            "vat_amount": "3.26",
            "total_amount": "25.00",
            "quantity": 1,
            "description": "Starter pack — AI credit pack",
            "description_ar": "Starter pack — حزمة أرصدة ذكاء اصطناعي",
            "seller": {
                "name": "Geem",
                "name_ar": "جيم",
                "vat_number": "399999999900003",
                "cr_number": "1234567890",
                "address": "Kingdom of Saudi Arabia",
                "address_ar": "المملكة العربية السعودية",
            },
            "buyer": {"name": "Acme", "workspace_slug": "acme"},
            "zatca_qr": zatca_qr_base64(
                seller_name="جيم",
                vat_number="399999999900003",
                timestamp="2026-08-18T17:02:00+03:00",
                total_with_vat="25.00",
                vat_amount="3.26",
            ),
            "sample": True,
        }
    )
    assert pdf.startswith(b"%PDF")
    from pypdf import PdfReader

    text = "".join(page.extract_text() or "" for page in PdfReader(io_bytes(pdf)).pages)
    assert "Simplified Tax Invoice" in text
    assert "GEEM-000001" in text
    assert "399999999900003" in text
    assert "25.00" in text
    assert "3.26" in text


def io_bytes(data: bytes):
    import io

    return io.BytesIO(data)
