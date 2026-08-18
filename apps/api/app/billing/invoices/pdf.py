"""Bilingual ZATCA simplified tax invoice PDF (Phase 1 generation)."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Any

from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
FONT_AR = "NotoNaskhArabic"
FONT_AR_BOLD = "NotoNaskhArabic-Bold"
FONT_EN = "Helvetica"
FONT_EN_BOLD = "Helvetica-Bold"

NAVY = HexColor("#0B1F3A")
RULE = HexColor("#D6D3D1")
MUTED = HexColor("#57534E")
BOX = HexColor("#F5F5F4")


@lru_cache(maxsize=1)
def _register_fonts() -> None:
    regular = FONTS_DIR / "NotoNaskhArabic-Regular.ttf"
    bold = FONTS_DIR / "NotoNaskhArabic-Bold.ttf"
    if not regular.is_file():
        raise FileNotFoundError(f"Missing invoice font: {regular}")
    pdfmetrics.registerFont(TTFont(FONT_AR, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_AR_BOLD, str(bold if bold.is_file() else regular)))


def _shape_ar(text: str) -> str:
    if not text:
        return ""
    from arabic_reshaper import reshape

    try:
        from bidi.algorithm import get_display
    except ImportError:
        from bidi import get_display

    return get_display(reshape(text))


def _qr_image(payload: str) -> ImageReader:
    import segno

    buf = io.BytesIO()
    segno.make(payload, error="m").save(buf, kind="png", scale=6, border=1)
    buf.seek(0)
    return ImageReader(buf)


def _en(c: canvas.Canvas, size: float, *, bold: bool = False) -> None:
    c.setFont(FONT_EN_BOLD if bold else FONT_EN, size)


def _ar(c: canvas.Canvas, size: float, *, bold: bool = False) -> None:
    c.setFont(FONT_AR_BOLD if bold else FONT_AR, size)


def _draw_label_pair(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    en: str,
    ar: str,
    value_en: str,
    value_ar: str = "",
    size: float = 8.5,
) -> None:
    c.setFillColor(MUTED)
    _en(c, 7)
    c.drawString(x, y + 12, en)
    _ar(c, 7)
    c.drawRightString(x + width, y + 12, _shape_ar(ar))
    c.setFillColor(black)
    _en(c, size, bold=True)
    c.drawString(x, y, value_en)
    if value_ar:
        _ar(c, size)
        c.drawRightString(x + width, y, _shape_ar(value_ar))


def render_simplified_tax_invoice(snapshot: dict[str, Any]) -> bytes:
    _register_fonts()
    seller = snapshot.get("seller") or {}
    buyer = snapshot.get("buyer") or {}
    number = str(snapshot.get("invoice_number") or "")
    issued = str(snapshot.get("issued_at") or "")
    currency = str(snapshot.get("currency") or "SAR")
    vat_rate = snapshot.get("vat_rate") or "0.15"
    try:
        vat_pct = f"{float(vat_rate) * 100:.0f}%"
    except (TypeError, ValueError):
        vat_pct = "15%"
    taxable = str(snapshot.get("taxable_amount") or "")
    vat_amount = str(snapshot.get("vat_amount") or "")
    total = str(snapshot.get("total_amount") or "")
    desc = str(snapshot.get("description") or "")
    desc_ar = str(snapshot.get("description_ar") or "")
    qty = str(snapshot.get("quantity") or 1)
    sample = bool(snapshot.get("sample"))
    qr = str(snapshot.get("zatca_qr") or "")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 16 * mm

    c.setFillColor(NAVY)
    c.rect(0, height - 28 * mm, width, 28 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    _en(c, 16, bold=True)
    c.drawString(margin, height - 14 * mm, str(seller.get("name") or "Geem"))
    _ar(c, 13, bold=True)
    c.drawRightString(
        width - margin - 32 * mm,
        height - 14 * mm,
        _shape_ar(str(seller.get("name_ar") or "جيم")),
    )
    _en(c, 8)
    c.drawString(margin, height - 20 * mm, "Simplified Tax Invoice")
    _ar(c, 8)
    c.drawRightString(
        width - margin - 32 * mm,
        height - 20 * mm,
        _shape_ar("فاتورة ضريبية مبسطة"),
    )

    if qr:
        qr_size = 28 * mm
        c.setFillColor(white)
        c.roundRect(
            width - margin - qr_size - 2 * mm,
            height - 30 * mm,
            qr_size + 4 * mm,
            qr_size + 4 * mm,
            2 * mm,
            fill=1,
            stroke=0,
        )
        c.drawImage(
            _qr_image(qr),
            width - margin - qr_size,
            height - 28 * mm,
            width=qr_size,
            height=qr_size,
            mask="auto",
            preserveAspectRatio=True,
        )

    y = height - 40 * mm
    c.setFillColor(black)
    _en(c, 14, bold=True)
    c.drawCentredString(width / 2, y, "Simplified Tax Invoice")
    y -= 6 * mm
    _ar(c, 14, bold=True)
    c.drawCentredString(width / 2, y, _shape_ar("فاتورة ضريبية مبسطة"))

    y -= 12 * mm
    col_w = (width - 2 * margin - 8 * mm) / 2
    box_h = 38 * mm
    for i, (title_en, title_ar, lines) in enumerate(
        (
            (
                "Seller / Supplier",
                "المورد",
                [
                    (str(seller.get("name") or ""), str(seller.get("name_ar") or "")),
                    (
                        f"VAT: {seller.get('vat_number') or '-'}",
                        f"الرقم الضريبي: {seller.get('vat_number') or '-'}",
                    ),
                    (
                        f"CR: {seller.get('cr_number')}" if seller.get("cr_number") else "",
                        f"س.ت: {seller.get('cr_number')}" if seller.get("cr_number") else "",
                    ),
                    (str(seller.get("address") or ""), str(seller.get("address_ar") or "")),
                ],
            ),
            (
                "Buyer / Customer",
                "العميل",
                [
                    (str(buyer.get("name") or ""), ""),
                    (f"Workspace: {buyer.get('workspace_slug') or '-'}", ""),
                ],
            ),
        )
    ):
        x = margin + i * (col_w + 8 * mm)
        c.setFillColor(BOX)
        c.roundRect(x, y - box_h + 8 * mm, col_w, box_h, 2 * mm, fill=1, stroke=0)
        c.setFillColor(NAVY)
        _en(c, 8, bold=True)
        c.drawString(x + 4 * mm, y, title_en)
        _ar(c, 8, bold=True)
        c.drawRightString(x + col_w - 4 * mm, y, _shape_ar(title_ar))
        c.setFillColor(black)
        text_y = y - 6 * mm
        for en, ar in lines:
            if not en and not ar:
                continue
            _en(c, 8)
            c.drawString(x + 4 * mm, text_y, en[:64])
            if ar:
                _ar(c, 8)
                c.drawRightString(x + col_w - 4 * mm, text_y, _shape_ar(ar)[:40])
            text_y -= 5 * mm

    y = y - box_h - 4 * mm
    meta_w = width - 2 * margin
    _draw_label_pair(
        c,
        x=margin,
        y=y,
        width=meta_w / 2 - 4 * mm,
        en="Invoice number",
        ar="رقم الفاتورة",
        value_en=number,
    )
    _draw_label_pair(
        c,
        x=margin + meta_w / 2 + 4 * mm,
        y=y,
        width=meta_w / 2 - 4 * mm,
        en="Issue date (AST)",
        ar="تاريخ الإصدار",
        value_en=issued,
        size=8,
    )
    y -= 14 * mm
    _draw_label_pair(
        c,
        x=margin,
        y=y,
        width=meta_w / 2 - 4 * mm,
        en="Invoice type",
        ar="نوع الفاتورة",
        value_en="Simplified tax invoice (B2C)",
        value_ar="فاتورة ضريبية مبسطة",
        size=8,
    )
    _draw_label_pair(
        c,
        x=margin + meta_w / 2 + 4 * mm,
        y=y,
        width=meta_w / 2 - 4 * mm,
        en="VAT rate",
        ar="نسبة الضريبة",
        value_en=vat_pct,
    )

    y -= 16 * mm
    table_top = y
    c.setFillColor(NAVY)
    c.rect(margin, table_top - 8 * mm, meta_w, 10 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    _en(c, 7.5, bold=True)
    c.drawString(margin + 3 * mm, table_top - 5 * mm, "Description")
    c.drawRightString(margin + meta_w * 0.52, table_top - 5 * mm, "Qty")
    c.drawRightString(margin + meta_w * 0.62, table_top - 5 * mm, "Taxable")
    c.drawRightString(margin + meta_w * 0.76, table_top - 5 * mm, f"VAT {vat_pct}")
    c.drawRightString(margin + meta_w - 3 * mm, table_top - 5 * mm, "Total incl. VAT")
    _ar(c, 7)
    c.drawRightString(margin + meta_w * 0.42, table_top - 5 * mm, _shape_ar("الوصف"))

    row_y = table_top - 18 * mm
    c.setFillColor(black)
    _en(c, 8)
    c.drawString(margin + 3 * mm, row_y + 4 * mm, desc[:70])
    if desc_ar:
        _ar(c, 8)
        c.drawString(margin + 3 * mm, row_y - 1 * mm, _shape_ar(desc_ar)[:48])
    _en(c, 8)
    c.drawRightString(margin + meta_w * 0.52, row_y + 2 * mm, qty)
    c.drawRightString(margin + meta_w * 0.62, row_y + 2 * mm, taxable)
    c.drawRightString(margin + meta_w * 0.76, row_y + 2 * mm, vat_amount)
    _en(c, 8, bold=True)
    c.drawRightString(margin + meta_w - 3 * mm, row_y + 2 * mm, f"{total} {currency}")
    c.setStrokeColor(RULE)
    c.setLineWidth(0.4)
    c.line(margin, row_y - 6 * mm, margin + meta_w, row_y - 6 * mm)

    totals_y = row_y - 16 * mm
    totals = [
        ("Taxable amount", "المبلغ الخاضع للضريبة", taxable),
        (f"VAT {vat_pct}", "ضريبة القيمة المضافة", vat_amount),
        ("Total incl. VAT", "الإجمالي شامل الضريبة", f"{total} {currency}"),
    ]
    for i, (label_en, label_ar, value) in enumerate(totals):
        ty = totals_y - i * 8 * mm
        bold = i == 2
        c.setFillColor(black)
        _en(c, 9 if bold else 8, bold=bold)
        c.drawRightString(margin + meta_w - 3 * mm, ty, value)
        _en(c, 8, bold=bold)
        c.drawString(margin + meta_w - 70 * mm, ty, label_en)
        _ar(c, 8, bold=bold)
        c.drawRightString(margin + meta_w - 42 * mm, ty, _shape_ar(label_ar))

    footer_y = 22 * mm
    c.setStrokeColor(RULE)
    c.line(margin, footer_y + 12 * mm, width - margin, footer_y + 12 * mm)
    c.setFillColor(MUTED)
    _en(c, 7)
    c.drawString(
        margin,
        footer_y + 6 * mm,
        "This is a simplified tax invoice issued in accordance with the VAT Implementing Regulation of the Kingdom of Saudi Arabia.",
    )
    _ar(c, 7)
    c.drawRightString(
        width - margin,
        footer_y,
        _shape_ar(
            "هذه فاتورة ضريبية مبسطة صادرة وفقاً للائحة التنفيذية لضريبة القيمة المضافة في المملكة العربية السعودية."
        ),
    )
    _en(c, 6.5)
    c.drawString(
        margin,
        footer_y - 5 * mm,
        "ZATCA Phase 1 QR encodes seller name, VAT number, timestamp, total, and VAT amount.",
    )

    if sample:
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(35)
        c.setFillColor(Color(0.7, 0.1, 0.1, alpha=0.18))
        _en(c, 42, bold=True)
        c.drawCentredString(0, 0, "SAMPLE")
        _ar(c, 22, bold=True)
        c.drawCentredString(0, -16 * mm, _shape_ar("عينة — ليست فاتورة معتمدة"))
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()
