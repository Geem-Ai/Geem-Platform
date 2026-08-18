"""Issue an immutable simplified-tax-invoice snapshot on a paid purchase."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.invoices.seller import SellerProfile, seller_profile
from app.billing.invoices.tax import format_sar, parse_vat_rate, split_vat
from app.billing.invoices.zatca import zatca_qr_base64
from app.billing.models import PURCHASE_INVOICE_SEQ, Purchase, PurchaseStatus
from app.billing.purchase_view import purchase_catalog_fields
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.workspaces.models import Workspace

KIND_LABEL_EN = {
    "subscription": "Workspace subscription",
    "credit_pack": "AI credit pack",
    "app_one_time": "App one-time purchase",
    "app_subscription": "App subscription",
    "app_subscription_renewal": "App subscription renewal",
}

KIND_LABEL_AR = {
    "subscription": "اشتراك مساحة العمل",
    "credit_pack": "حزمة أرصدة ذكاء اصطناعي",
    "app_one_time": "شراء تطبيق لمرة واحدة",
    "app_subscription": "اشتراك تطبيق",
    "app_subscription_renewal": "تجديد اشتراك تطبيق",
}


def _riyadh_tz():
    try:
        return ZoneInfo("Asia/Riyadh")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3))


def _issued_at(purchase: Purchase) -> datetime:
    raw = purchase.paid_at or purchase.created_at
    if raw.tzinfo is None:
        return raw.replace(tzinfo=timezone.utc)
    return raw


def _iso_riyadh(value: datetime) -> str:
    return value.astimezone(_riyadh_tz()).isoformat(timespec="seconds")


def _line_descriptions(purchase: Purchase) -> tuple[str, str]:
    fields = purchase_catalog_fields(purchase)
    kind_en = KIND_LABEL_EN.get(purchase.kind, "Purchase")
    kind_ar = KIND_LABEL_AR.get(purchase.kind, "شراء")
    name = (fields.item_name or "").strip()
    if name:
        extra = ""
        if fields.credits and purchase.kind == "credit_pack":
            extra = f" ({int(fields.credits)} AI credits)"
        return f"{name} — {kind_en}{extra}", f"{name} — {kind_ar}"
    return kind_en, kind_ar


def _next_invoice_number(db: Session) -> str:
    n = db.scalar(select(PURCHASE_INVOICE_SEQ.next_value()))
    if n is None:
        raise AppError(ErrorCategory.INVOICE_NOT_CONFIGURED, "Invoice sequence is unavailable.")
    return f"GEEM-{int(n):06d}"


def _snapshot_dict(
    *,
    invoice_number: str,
    purchase: Purchase,
    workspace: Workspace,
    seller: SellerProfile,
    settings: Settings,
) -> dict[str, Any]:
    rate = parse_vat_rate(settings.invoice_vat_rate)
    taxable, vat, total = split_vat(
        amount=purchase.amount,
        rate=rate,
        prices_include_vat=bool(settings.invoice_prices_include_vat),
    )
    issued = _issued_at(purchase)
    timestamp = _iso_riyadh(issued)
    desc_en, desc_ar = _line_descriptions(purchase)
    qr_name = seller.name_ar or seller.name
    qr = zatca_qr_base64(
        seller_name=qr_name,
        vat_number=seller.vat_number,
        timestamp=timestamp,
        total_with_vat=format_sar(total),
        vat_amount=format_sar(vat),
    )
    return {
        "invoice_number": invoice_number,
        "invoice_type": "simplified_tax_invoice",
        "currency": purchase.currency,
        "issued_at": timestamp,
        "vat_rate": str(rate),
        "prices_include_vat": bool(settings.invoice_prices_include_vat),
        "taxable_amount": format_sar(taxable),
        "vat_amount": format_sar(vat),
        "total_amount": format_sar(total),
        "quantity": 1,
        "unit_price_ex_vat": format_sar(taxable),
        "description": desc_en,
        "description_ar": desc_ar,
        "purchase_id": str(purchase.id),
        "seller": {
            "name": seller.name,
            "name_ar": seller.name_ar,
            "vat_number": seller.vat_number,
            "cr_number": seller.cr_number,
            "address": seller.address,
            "address_ar": seller.address_ar,
        },
        "buyer": {
            "name": workspace.name,
            "workspace_slug": workspace.slug,
        },
        "zatca_qr": qr,
        "sample": seller.sample,
    }


class InvoiceService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def issue_for_purchase(self, purchase: Purchase) -> dict[str, Any]:
        """Assign invoice number + freeze tax fields. Idempotent once issued."""
        if purchase.status != PurchaseStatus.PAID.value:
            raise AppError(
                ErrorCategory.INVOICE_NOT_AVAILABLE,
                "An invoice is available only after payment is verified.",
            )
        existing = purchase.invoice_snapshot if isinstance(purchase.invoice_snapshot, dict) else None
        if purchase.invoice_number and existing:
            return existing
        workspace = self.db.get(Workspace, purchase.workspace_id)
        if workspace is None:
            raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")
        seller = seller_profile(self.settings)
        number = purchase.invoice_number or _next_invoice_number(self.db)
        snapshot = _snapshot_dict(
            invoice_number=number,
            purchase=purchase,
            workspace=workspace,
            seller=seller,
            settings=self.settings,
        )
        purchase.invoice_number = number
        purchase.invoice_snapshot = snapshot
        self.db.flush()
        return snapshot

    def pdf_for_workspace(self, workspace: Workspace, purchase_id) -> tuple[bytes, str]:
        try:
            from app.billing.invoices.pdf import render_simplified_tax_invoice
        except ImportError as exc:
            raise AppError(
                ErrorCategory.INVOICE_NOT_CONFIGURED,
                "Invoice PDF renderer is not installed on this server.",
            ) from exc

        purchase = self.db.scalar(
            select(Purchase)
            .where(
                Purchase.id == purchase_id,
                Purchase.workspace_id == workspace.id,
            )
            .with_for_update()
        )
        if purchase is None:
            raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")
        snapshot = self.issue_for_purchase(purchase)
        try:
            pdf = render_simplified_tax_invoice(snapshot)
        except FileNotFoundError as exc:
            raise AppError(
                ErrorCategory.INVOICE_NOT_CONFIGURED,
                "Invoice fonts are missing from the API image.",
            ) from exc
        number = snapshot["invoice_number"]
        return pdf, f"{number}.pdf"
