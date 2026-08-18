"""Bilingual ZATCA simplified tax invoice PDF (Phase 1 generation)."""

from __future__ import annotations

import io
import re
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
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "geem-logo.png"
RIYAL_SVG_PATH = ASSETS_DIR / "saudi-riyal.svg"

FONT_AR = "NotoNaskhArabic"
FONT_AR_BOLD = "NotoNaskhArabic-Bold"
FONT_EN = "Helvetica"
FONT_EN_BOLD = "Helvetica-Bold"

NAVY = HexColor("#0E2F44")
NAVY_SOFT = HexColor("#163C54")
RULE = HexColor("#E7E5E4")
MUTED = HexColor("#57534E")
BOX = HexColor("#F5F5F4")
TOTALS_BG = HexColor("#F8FAFC")

RIYAL_VIEWBOX = (1124.14, 1256.39)
_PATH_TOKENS = re.compile(
    r"[A-Za-z]|[+-]?(?:\d*\.\d+|\d+)(?:[eE][+-]?\d+)?"
)
_SVG_PATH_D = re.compile(r'<path\s[^>]*d="([^"]+)"')


@lru_cache(maxsize=1)
def _register_fonts() -> None:
    regular = FONTS_DIR / "NotoNaskhArabic-Regular.ttf"
    bold = FONTS_DIR / "NotoNaskhArabic-Bold.ttf"
    if not regular.is_file():
        raise FileNotFoundError(f"Missing invoice font: {regular}")
    pdfmetrics.registerFont(TTFont(FONT_AR, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_AR_BOLD, str(bold if bold.is_file() else regular)))


@lru_cache(maxsize=1)
def _riyal_paths() -> tuple[str, ...]:
    raw = RIYAL_SVG_PATH.read_text(encoding="utf-8")
    found = _SVG_PATH_D.findall(raw)
    if not found:
        raise FileNotFoundError(f"Saudi riyal SVG has no paths: {RIYAL_SVG_PATH}")
    return tuple(found)


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


def _fit(text: str, font: str, size: float, max_width: float) -> str:
    if not text:
        return ""
    while text and pdfmetrics.stringWidth(text, font, size) > max_width:
        text = text[:-1]
    return text


def _add_svg_path(path: Any, d: str) -> None:
    tokens = _PATH_TOKENS.findall(d)
    i = 0
    x = y = 0.0
    sx = sy = 0.0
    prev = ""

    def take(n: int) -> list[float]:
        nonlocal i
        vals = [float(tokens[i + k]) for k in range(n)]
        i += n
        return vals

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
        else:
            cmd = "L" if prev == "M" else "l" if prev == "m" else prev
        prev = cmd

        if cmd == "M":
            x, y = take(2)
            path.moveTo(x, y)
            sx, sy = x, y
        elif cmd == "m":
            dx, dy = take(2)
            x, y = x + dx, y + dy
            path.moveTo(x, y)
            sx, sy = x, y
        elif cmd == "L":
            x, y = take(2)
            path.lineTo(x, y)
        elif cmd == "l":
            dx, dy = take(2)
            x, y = x + dx, y + dy
            path.lineTo(x, y)
        elif cmd == "H":
            x = take(1)[0]
            path.lineTo(x, y)
        elif cmd == "h":
            x += take(1)[0]
            path.lineTo(x, y)
        elif cmd == "V":
            y = take(1)[0]
            path.lineTo(x, y)
        elif cmd == "v":
            y += take(1)[0]
            path.lineTo(x, y)
        elif cmd == "C":
            x1, y1, x2, y2, x, y = take(6)
            path.curveTo(x1, y1, x2, y2, x, y)
        elif cmd == "c":
            x1, y1, x2, y2, dx, dy = take(6)
            path.curveTo(x + x1, y + y1, x + x2, y + y2, x + dx, y + dy)
            x, y = x + dx, y + dy
        elif cmd in ("Z", "z"):
            path.close()
            x, y = sx, sy
        else:
            raise ValueError(f"Unsupported SVG path command: {cmd}")


def _draw_riyal(
    c: canvas.Canvas,
    x: float,
    y: float,
    height: float,
    color: Any,
) -> float:
    """Draw the official Saudi riyal symbol. Returns the drawn width."""
    vb_w, vb_h = RIYAL_VIEWBOX
    scale = height / vb_h
    width = vb_w * scale
    p = c.beginPath()
    for d in _riyal_paths():
        _add_svg_path(p, d)
    c.saveState()
    c.setFillColor(color)
    c.translate(x, y + height)
    c.scale(scale, -scale)
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()
    return width


def _draw_money(
    c: canvas.Canvas,
    *,
    right: float,
    y: float,
    amount: str,
    currency: str,
    size: float = 9,
    bold: bool = False,
    color: Any = black,
) -> None:
    font = FONT_EN_BOLD if bold else FONT_EN
    c.setFillColor(color)
    _en(c, size, bold=bold)
    if currency.upper() != "SAR":
        c.drawRightString(right, y, f"{currency} {amount}")
        return
    c.drawRightString(right, y, amount)
    amt_w = pdfmetrics.stringWidth(amount, font, size)
    icon_h = size * 1.05
    gap = 1.15
    icon_w = icon_h * (RIYAL_VIEWBOX[0] / RIYAL_VIEWBOX[1])
    _draw_riyal(c, right - amt_w - gap - icon_w, y - 0.35, icon_h, color)


def _draw_logo(c: canvas.Canvas, x: float, y: float, box_w: float, box_h: float) -> None:
    if not LOGO_PATH.is_file():
        return
    c.setFillColor(white)
    c.roundRect(x, y, box_w, box_h, 2.2 * mm, fill=1, stroke=0)
    pad = 1.2 * mm
    c.drawImage(
        str(LOGO_PATH),
        x + pad,
        y + pad,
        width=box_w - 2 * pad,
        height=box_h - 2 * pad,
        mask="auto",
        preserveAspectRatio=True,
        anchor="c",
    )


def _header(
    c: canvas.Canvas,
    *,
    width: float,
    height: float,
    margin: float,
    seller: dict[str, Any],
    qr: str,
) -> float:
    header_h = 36 * mm
    c.setFillColor(NAVY)
    c.rect(0, height - header_h, width, header_h, fill=1, stroke=0)
    c.setFillColor(NAVY_SOFT)
    c.rect(0, height - header_h, width, 1.1 * mm, fill=1, stroke=0)

    logo_w, logo_h = 18 * mm, 30 * mm
    logo_x = margin
    logo_y = height - header_h + 4 * mm
    _draw_logo(c, logo_x, logo_y, logo_w, logo_h)

    text_x = logo_x + logo_w + 5 * mm
    qr_size = 26 * mm
    qr_left = width - margin - qr_size - 3 * mm
    name_right = qr_left - 6 * mm
    text_w = max(name_right - text_x, 20 * mm)
    name_en = str(seller.get("name") or "Geem")
    name_ar = str(seller.get("name_ar") or "جيم")
    shaped_ar = _shape_ar(name_ar)

    def _fit_size(text: str, font: str, start: float) -> float:
        size = start
        while size > 8 and pdfmetrics.stringWidth(text, font, size) > text_w:
            size -= 0.5
        return size

    en_size = _fit_size(name_en, FONT_EN_BOLD, 12)
    ar_size = _fit_size(shaped_ar, FONT_AR_BOLD, 11)

    c.setFillColor(white)
    _en(c, en_size, bold=True)
    c.drawString(text_x, height - 12.5 * mm, _fit(name_en, FONT_EN_BOLD, en_size, text_w))
    _ar(c, ar_size, bold=True)
    c.drawRightString(name_right, height - 19.5 * mm, _fit(shaped_ar, FONT_AR_BOLD, ar_size, text_w))
    _en(c, 8)
    c.drawString(text_x, height - 27 * mm, "Simplified Tax Invoice")
    _ar(c, 8)
    c.drawRightString(name_right, height - 27 * mm, _shape_ar("فاتورة ضريبية مبسطة"))

    if qr:
        card = qr_size + 5 * mm
        c.setFillColor(white)
        c.roundRect(
            width - margin - card,
            height - header_h + 3 * mm,
            card,
            card,
            2 * mm,
            fill=1,
            stroke=0,
        )
        c.drawImage(
            _qr_image(qr),
            width - margin - card + 2.5 * mm,
            height - header_h + 5.5 * mm,
            width=qr_size,
            height=qr_size,
            mask="auto",
            preserveAspectRatio=True,
        )
    return height - header_h - 8 * mm


def _party_card(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    title_en: str,
    title_ar: str,
    lines: list[tuple[str, str]],
) -> None:
    c.setFillColor(BOX)
    c.roundRect(x, y - height, width, height, 2.2 * mm, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.rect(x, y - height, 1.4 * mm, height, fill=1, stroke=0)
    c.setFillColor(NAVY)
    _en(c, 8, bold=True)
    c.drawString(x + 5 * mm, y - 6 * mm, title_en)
    _ar(c, 8, bold=True)
    c.drawRightString(x + width - 4 * mm, y - 6 * mm, _shape_ar(title_ar))
    inner = width - 9 * mm
    text_y = y - 13.5 * mm
    for en, ar in lines:
        if not en and not ar:
            continue
        if en:
            c.setFillColor(black)
            _en(c, 8)
            c.drawString(x + 5 * mm, text_y, _fit(en, FONT_EN, 8, inner))
            text_y -= 4.2 * mm
        if ar:
            c.setFillColor(MUTED)
            _ar(c, 8)
            c.drawRightString(x + width - 4 * mm, text_y, _shape_ar(ar)[:42])
            text_y -= 5.2 * mm


def _meta_cell(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    en: str,
    ar: str,
    value: str,
    value_ar: str = "",
) -> None:
    c.setFillColor(MUTED)
    _en(c, 7)
    c.drawString(x, y + 11, en)
    _ar(c, 7)
    c.drawRightString(x + width, y + 11, _shape_ar(ar))
    c.setFillColor(black)
    _en(c, 9, bold=True)
    c.drawString(x, y, _fit(value, FONT_EN_BOLD, 9, width))
    if value_ar:
        _ar(c, 8)
        c.drawString(x, y - 11, _shape_ar(value_ar))


def _table_header_cell(
    c: canvas.Canvas,
    *,
    x: float,
    y: float,
    en: str,
    ar: str,
    right: bool,
) -> None:
    c.setFillColor(white)
    _en(c, 7, bold=True)
    if right:
        c.drawRightString(x, y + 3.6 * mm, en)
    else:
        c.drawString(x, y + 3.6 * mm, en)
    _ar(c, 7)
    if right:
        c.drawRightString(x, y - 2.0 * mm, _shape_ar(ar))
    else:
        c.drawString(x, y - 2.0 * mm, _shape_ar(ar))


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
    margin = 15 * mm
    content_w = width - 2 * margin

    y = _header(c, width=width, height=height, margin=margin, seller=seller, qr=qr)

    col_w = (content_w - 6 * mm) / 2
    box_h = 48 * mm
    vat_no = str(seller.get("vat_number") or "-")
    cr = str(seller.get("cr_number") or "")
    ws_slug = str(buyer.get("workspace_slug") or "-")
    _party_card(
        c,
        x=margin,
        y=y,
        width=col_w,
        height=box_h,
        title_en="Seller / Supplier",
        title_ar="المورد",
        lines=[
            (str(seller.get("name") or ""), str(seller.get("name_ar") or "")),
            (f"VAT {vat_no}", "الرقم الضريبي"),
            (f"CR {cr}" if cr else "", "السجل التجاري" if cr else ""),
            (str(seller.get("address") or ""), str(seller.get("address_ar") or "")),
        ],
    )
    _party_card(
        c,
        x=margin + col_w + 6 * mm,
        y=y,
        width=col_w,
        height=box_h,
        title_en="Buyer / Customer",
        title_ar="العميل",
        lines=[
            (str(buyer.get("name") or ""), ""),
            (f"Workspace: {ws_slug}", f"مساحة العمل: {ws_slug}"),
        ],
    )

    y -= box_h + 8 * mm
    meta_h = 18 * mm
    c.setFillColor(BOX)
    c.roundRect(margin, y - meta_h, content_w, meta_h, 2 * mm, fill=1, stroke=0)
    cell_w = (content_w - 16 * mm) / 2
    _meta_cell(
        c,
        x=margin + 5 * mm,
        y=y - 8 * mm,
        width=cell_w,
        en="Invoice number",
        ar="رقم الفاتورة",
        value=number,
    )
    _meta_cell(
        c,
        x=margin + 11 * mm + cell_w,
        y=y - 8 * mm,
        width=cell_w,
        en="Issue date (AST)",
        ar="تاريخ الإصدار",
        value=issued,
    )
    y -= meta_h + 7 * mm
    _meta_cell(
        c,
        x=margin,
        y=y,
        width=cell_w,
        en="Invoice type",
        ar="نوع الفاتورة",
        value="Simplified tax invoice (B2C)",
    )
    _meta_cell(
        c,
        x=margin + content_w - cell_w,
        y=y,
        width=cell_w,
        en="VAT rate",
        ar="نسبة الضريبة",
        value=vat_pct,
    )

    y -= 12 * mm
    header_h = 13.5 * mm
    c.setFillColor(NAVY)
    c.roundRect(margin, y - header_h, content_w, header_h, 2 * mm, fill=1, stroke=0)
    c.rect(margin, y - header_h, content_w, 4 * mm, fill=1, stroke=0)
    mid = y - header_h / 2
    cols = {
        "desc": margin + 3.5 * mm,
        "qty": margin + content_w * 0.46,
        "taxable": margin + content_w * 0.60,
        "vat": margin + content_w * 0.76,
        "total": margin + content_w - 3.5 * mm,
    }
    _table_header_cell(c, x=cols["desc"], y=mid, en="Description", ar="الوصف", right=False)
    _table_header_cell(c, x=cols["qty"], y=mid, en="Qty", ar="الكمية", right=True)
    _table_header_cell(c, x=cols["taxable"], y=mid, en="Taxable", ar="الخاضع للضريبة", right=True)
    _table_header_cell(c, x=cols["vat"], y=mid, en=f"VAT {vat_pct}", ar="ضريبة ١٥٪", right=True)
    _table_header_cell(
        c, x=cols["total"], y=mid, en="Total incl. VAT", ar="الإجمالي شامل الضريبة", right=True
    )

    row_h = 16 * mm
    row_top = y - header_h
    c.setFillColor(HexColor("#FAFAF9"))
    c.rect(margin, row_top - row_h, content_w, row_h, fill=1, stroke=0)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.4)
    c.line(margin, row_top - row_h, margin + content_w, row_top - row_h)
    row_mid = row_top - 7 * mm
    c.setFillColor(black)
    _en(c, 8)
    c.drawString(cols["desc"], row_mid + 2.2 * mm, _fit(desc, FONT_EN, 8, content_w * 0.40))
    if desc_ar:
        c.setFillColor(MUTED)
        _ar(c, 8)
        c.drawString(cols["desc"], row_mid - 3.2 * mm, _shape_ar(desc_ar)[:42])
    c.setFillColor(black)
    _en(c, 8)
    c.drawRightString(cols["qty"], row_mid, qty)
    _draw_money(c, right=cols["taxable"], y=row_mid, amount=taxable, currency=currency, size=8)
    _draw_money(c, right=cols["vat"], y=row_mid, amount=vat_amount, currency=currency, size=8)
    _draw_money(c, right=cols["total"], y=row_mid, amount=total, currency=currency, size=8.5, bold=True)

    totals_w = 92 * mm
    totals_x = margin + content_w - totals_w
    totals_y = row_top - row_h - 6 * mm
    rows = [
        ("Taxable amount", "المبلغ الخاضع للضريبة", taxable, False),
        (f"VAT {vat_pct}", "ضريبة القيمة المضافة", vat_amount, False),
        ("Total incl. VAT", "الإجمالي شامل الضريبة", total, True),
    ]
    row_heights = [16 * mm, 16 * mm, 18 * mm]
    box_h = sum(row_heights) + 4 * mm
    c.setFillColor(TOTALS_BG)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.roundRect(totals_x, totals_y - box_h, totals_w, box_h, 2.2 * mm, fill=1, stroke=1)

    cursor = totals_y - 2 * mm
    for (label_en, label_ar, value, emphasize), rh in zip(rows, row_heights):
        cursor -= rh
        label_x = totals_x + 4 * mm
        amount_right = totals_x + totals_w - 4 * mm
        if emphasize:
            c.setFillColor(NAVY)
            c.roundRect(totals_x + 1.2 * mm, cursor, totals_w - 2.4 * mm, rh - 1.2 * mm, 1.6 * mm, fill=1, stroke=0)
            c.setFillColor(white)
            _en(c, 8, bold=True)
            c.drawString(label_x, cursor + 10.2 * mm, label_en)
            _ar(c, 8, bold=True)
            c.drawString(label_x, cursor + 3.4 * mm, _shape_ar(label_ar))
            _draw_money(
                c,
                right=amount_right,
                y=cursor + 6.4 * mm,
                amount=value,
                currency=currency,
                size=10,
                bold=True,
                color=white,
            )
        else:
            c.setFillColor(MUTED)
            _en(c, 8)
            c.drawString(label_x, cursor + 9.6 * mm, label_en)
            c.setFillColor(black)
            _ar(c, 8)
            c.drawString(label_x, cursor + 3.0 * mm, _shape_ar(label_ar))
            _draw_money(
                c,
                right=amount_right,
                y=cursor + 6.0 * mm,
                amount=value,
                currency=currency,
                size=9,
            )
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.line(totals_x + 4 * mm, cursor, totals_x + totals_w - 4 * mm, cursor)

    footer_y = 18 * mm
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(margin, footer_y + 14 * mm, width - margin, footer_y + 14 * mm)
    c.setFillColor(MUTED)
    _en(c, 7)
    c.drawString(
        margin,
        footer_y + 8 * mm,
        "This is a simplified tax invoice issued in accordance with the VAT Implementing Regulation",
    )
    _en(c, 7)
    c.drawString(margin, footer_y + 4.4 * mm, "of the Kingdom of Saudi Arabia.")
    _ar(c, 7)
    c.drawRightString(
        width - margin,
        footer_y - 1.2 * mm,
        _shape_ar(
            "هذه فاتورة ضريبية مبسطة صادرة وفقاً للائحة التنفيذية لضريبة القيمة المضافة في المملكة العربية السعودية."
        ),
    )

    if sample:
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(35)
        c.setFillColor(Color(0.7, 0.1, 0.1, alpha=0.16))
        _en(c, 42, bold=True)
        c.drawCentredString(0, 0, "SAMPLE")
        _ar(c, 22, bold=True)
        c.drawCentredString(0, -16 * mm, _shape_ar("عينة — ليست فاتورة معتمدة"))
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()
