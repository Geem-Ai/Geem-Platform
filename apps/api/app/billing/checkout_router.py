"""Workspace billing catalog, checkout, and gateway return (Phase 6A/6B)."""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.billing.checkout import BillingService
from app.billing.invoices.service import InvoiceService
from app.billing.models import (
    CreditPack,
    Plan,
    Purchase,
    PurchaseStatus,
)
from app.billing.purchase_view import purchase_catalog_fields
from app.billing.schemas import (
    CheckoutOut,
    CreditPackCheckoutRequest,
    CreditPackOut,
    EntitlementItemOut,
    PurchasablePlanOut,
    PurchaseListOut,
    PurchaseOut,
    SubscriptionCheckoutRequest,
)
from app.common.http import content_disposition
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCategory
from app.db.session import get_db
from app.entitlements.keys import entitlement_display_sort_key
from app.entitlements.values import entitlement_value_from_row
from app.identity.dependencies import client_ip, get_current_user
from app.identity.models import User
from app.workspaces.dependencies import require_workspace, require_workspace_action
from app.workspaces.models import Workspace, WorkspaceMembership
from app.workspaces.policy import WorkspaceAction

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _plan_entitlements(plan: Plan) -> list[EntitlementItemOut]:
    items: list[EntitlementItemOut] = []
    for row in sorted(plan.entitlements, key=lambda r: entitlement_display_sort_key(r.key)):
        try:
            value = entitlement_value_from_row(
                key=row.key,
                raw=row.value,
                value_type=row.value_type,
            )
            items.append(
                EntitlementItemOut(
                    key=value.key,
                    value=value.as_python(),
                    value_type=value.value_type.value,
                )
            )
        except AppError:
            continue
    return items


def _plan_out(plan: Plan) -> PurchasablePlanOut:
    return PurchasablePlanOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        status=plan.status,
        price_amount=str(plan.price_amount),
        currency=plan.currency,
        entitlements=_plan_entitlements(plan),
    )


def _pack_out(pack: CreditPack) -> CreditPackOut:
    return CreditPackOut(
        id=pack.id,
        code=pack.code,
        name=pack.name,
        description=pack.description,
        credits=int(pack.credits),
        price_amount=str(pack.price_amount),
        currency=pack.currency,
        active=pack.active,
    )


def _checkout_out(purchase: Purchase) -> CheckoutOut:
    if not purchase.redirect_url:
        raise AppError(
            ErrorCategory.BILLING_GATEWAY_ERROR,
            "Checkout did not produce a redirect URL.",
        )
    return CheckoutOut(
        purchase_id=purchase.id,
        status=purchase.status,
        kind=purchase.kind,
        amount=str(purchase.amount),
        currency=purchase.currency,
        redirect_url=purchase.redirect_url,
    )


def _purchase_out(purchase: Purchase) -> PurchaseOut:
    fields = purchase_catalog_fields(purchase)
    return PurchaseOut(
        id=purchase.id,
        status=purchase.status,
        kind=purchase.kind,
        amount=str(purchase.amount),
        currency=purchase.currency,
        item_name=fields.item_name,
        item_code=fields.item_code,
        credits=fields.credits,
        app_slug=fields.app_slug,
        app_name=fields.app_name,
        commercial_action=fields.commercial_action,
        billing_interval=fields.billing_interval,
        paid_at=purchase.paid_at,
        created_at=purchase.created_at,
    )


def _wants_html_redirect(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept


def _spa_origin_from_request(request: Request) -> str | None:
    settings = get_settings()
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin and settings.is_allowed_spa_origin(origin):
        return origin
    return None


def _spa_payment_result_url(purchase: Purchase) -> str | None:
    settings = get_settings()
    stored = (purchase.extra or {}).get("spa_origin")
    base = ""
    if isinstance(stored, str) and settings.is_allowed_spa_origin(stored):
        base = stored.strip().rstrip("/")
    if not base:
        base = settings.effective_workspace_web_url
    if not base:
        return None
    app_kinds = {
        "app_one_time",
        "app_subscription",
        "app_subscription_renewal",
    }
    if purchase.kind in app_kinds:
        if purchase.status == PurchaseStatus.PAID.value:
            path = "/apps/payment/result"
        elif purchase.status in {
            PurchaseStatus.FAILED.value,
            PurchaseStatus.CANCELLED.value,
            PurchaseStatus.EXPIRED.value,
        }:
            path = "/apps/payment/result"
        else:
            path = "/apps/payment/result"
    elif purchase.status == PurchaseStatus.PAID.value:
        path = "/billing/payment/success"
    elif purchase.status in {
        PurchaseStatus.FAILED.value,
        PurchaseStatus.CANCELLED.value,
        PurchaseStatus.EXPIRED.value,
    }:
        path = "/billing/payment/failed"
    else:
        path = "/billing/payment/pending"
    query = urlencode({"purchase": str(purchase.id)})
    return f"{base}{path}?{query}"


@router.get("/plans", response_model=list[PurchasablePlanOut])
def list_plans(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.VIEW_BILLING)
    ),
    db: Session = Depends(get_db),
) -> list[PurchasablePlanOut]:
    _workspace, _membership = pair
    return [_plan_out(plan) for plan in BillingService(db).list_purchasable_plans()]


@router.get("/credit-packs", response_model=list[CreditPackOut])
def list_credit_packs(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.VIEW_BILLING)
    ),
    db: Session = Depends(get_db),
) -> list[CreditPackOut]:
    _workspace, _membership = pair
    return [_pack_out(pack) for pack in BillingService(db).list_active_credit_packs()]


@router.post("/checkout/subscription", response_model=CheckoutOut)
def checkout_subscription(
    body: SubscriptionCheckoutRequest,
    request: Request,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.MANAGE_BILLING)
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    workspace, _membership = pair
    purchase, _token = BillingService(db).create_subscription_checkout(
        workspace,
        user,
        body.plan_id,
        customer_ip=client_ip(request),
        spa_origin=_spa_origin_from_request(request),
    )
    db.commit()
    return _checkout_out(purchase)


@router.post("/checkout/credit-packs", response_model=CheckoutOut)
def checkout_credit_pack(
    body: CreditPackCheckoutRequest,
    request: Request,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.PURCHASE_CREDITS)
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    workspace, _membership = pair
    purchase, _token = BillingService(db).create_credit_pack_checkout(
        workspace,
        user,
        body.credit_pack_id,
        customer_ip=client_ip(request),
        spa_origin=_spa_origin_from_request(request),
    )
    db.commit()
    return _checkout_out(purchase)


@router.get("/purchases", response_model=PurchaseListOut)
def list_purchases(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace_action(WorkspaceAction.VIEW_BILLING)),
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, max_length=32),
    kind: str | None = Query(default=None, max_length=32),
) -> PurchaseListOut:
    workspace, _membership = pair
    rows, total = BillingService(db).list_purchases_for_workspace(
        workspace,
        limit=limit,
        offset=offset,
        status=status,
        kind=kind,
    )
    return PurchaseListOut(
        items=[_purchase_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/purchases/{purchase_id}", response_model=PurchaseOut)
def get_purchase(
    purchase_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace_action(WorkspaceAction.VIEW_BILLING)),
    db: Session = Depends(get_db),
) -> PurchaseOut:
    workspace, _membership = pair
    purchase = BillingService(db).get_purchase_for_workspace(workspace, purchase_id)
    return _purchase_out(purchase)


@router.get("/purchases/{purchase_id}/invoice")
def download_purchase_invoice(
    purchase_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(
        require_workspace_action(WorkspaceAction.VIEW_BILLING)
    ),
    db: Session = Depends(get_db),
) -> Response:
    workspace, _membership = pair
    pdf, filename = InvoiceService(db).pdf_for_workspace(workspace, purchase_id)
    db.commit()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.api_route(
    "/return/{gateway_code}/{purchase_id}",
    methods=["GET", "POST"],
    response_model=None,
)
def billing_return(
    gateway_code: str,
    purchase_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    rt: str = Query(default="", alias="rt"),
) -> PurchaseOut | RedirectResponse:
    """Browser return from the hosted payment page.

    Query/body fields from the provider are ignored. Verification is a
    server-to-server transaction query using the stored tran_ref.

    Browsers (Accept: text/html) are redirected to the Workspace SPA with the
    purchase id as a lookup key only — never a trusted payment status.
    """
    purchase = BillingService(db).complete_on_return(
        purchase_id,
        return_token=rt,
        gateway_code=gateway_code,
    )
    db.commit()
    if _wants_html_redirect(request):
        spa_url = _spa_payment_result_url(purchase)
        if spa_url:
            return RedirectResponse(url=spa_url, status_code=303)
    return _purchase_out(purchase)
