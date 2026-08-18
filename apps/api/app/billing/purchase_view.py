"""Catalog fields derived from a purchase payload. Safe for Workspace DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.billing.models import Purchase


@dataclass(frozen=True)
class PurchaseCatalogFields:
    item_name: str | None
    item_code: str | None
    credits: int | None
    app_slug: str | None
    app_name: str | None
    commercial_action: str | None
    billing_interval: str | None


def _payload_int(payload: dict[str, Any], key: str) -> int | None:
    raw = payload.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        if isinstance(raw, str) and raw.lstrip("-").isdigit():
            return int(raw)
        return None
    return int(raw)


def purchase_catalog_fields(purchase: Purchase) -> PurchaseCatalogFields:
    payload = purchase.payload if isinstance(purchase.payload, dict) else {}
    item_code: str | None = None
    item_name: str | None = None
    credits: int | None = None
    app_slug: str | None = None
    app_name: str | None = None
    commercial_action: str | None = None
    billing_interval: str | None = None
    if purchase.kind == "subscription":
        item_code = payload.get("plan_code") if isinstance(payload.get("plan_code"), str) else None
        item_name = payload.get("plan_name") if isinstance(payload.get("plan_name"), str) else item_code
    elif purchase.kind == "credit_pack":
        item_code = (
            payload.get("credit_pack_code")
            if isinstance(payload.get("credit_pack_code"), str)
            else None
        )
        item_name = (
            payload.get("credit_pack_name")
            if isinstance(payload.get("credit_pack_name"), str)
            else item_code
        )
        credits = _payload_int(payload, "credits")
    elif purchase.kind in {
        "app_one_time",
        "app_subscription",
        "app_subscription_renewal",
    }:
        app_slug = payload.get("app_slug") if isinstance(payload.get("app_slug"), str) else None
        app_name = payload.get("app_name") if isinstance(payload.get("app_name"), str) else None
        plan_code = payload.get("plan_code") if isinstance(payload.get("plan_code"), str) else None
        plan_name = payload.get("plan_name") if isinstance(payload.get("plan_name"), str) else None
        item_code = plan_code
        if app_name and plan_name:
            item_name = f"{app_name} — {plan_name}"
        else:
            item_name = app_name or plan_name or plan_code
        commercial_action = (
            payload.get("commercial_action")
            if isinstance(payload.get("commercial_action"), str)
            else None
        )
        billing_interval = (
            payload.get("billing_interval")
            if isinstance(payload.get("billing_interval"), str)
            else None
        )
    return PurchaseCatalogFields(
        item_name=item_name,
        item_code=item_code,
        credits=credits,
        app_slug=app_slug,
        app_name=app_name,
        commercial_action=commercial_action,
        billing_interval=billing_interval,
    )
