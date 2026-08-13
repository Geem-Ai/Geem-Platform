"""Workspace billing catalog, checkout, and gateway return (Phase 6A)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.billing.checkout import BillingService
from app.billing.models import CreditPack, Plan, Purchase
from app.billing.schemas import (
    CheckoutOut,
    CreditPackCheckoutRequest,
    CreditPackOut,
    PurchasablePlanOut,
    PurchaseOut,
    SubscriptionCheckoutRequest,
)
from app.db.session import get_db
from app.identity.dependencies import client_ip, get_current_user
from app.identity.models import User
from app.workspaces.dependencies import require_workspace
from app.workspaces.models import Workspace, WorkspaceMembership

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _plan_out(plan: Plan) -> PurchasablePlanOut:
    return PurchasablePlanOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        status=plan.status,
        price_amount=str(plan.price_amount),
        currency=plan.currency,
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
        from app.core.errors import AppError, ErrorCategory

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
    return PurchaseOut(
        id=purchase.id,
        status=purchase.status,
        kind=purchase.kind,
        amount=str(purchase.amount),
        currency=purchase.currency,
        redirect_url=purchase.redirect_url,
        paid_at=purchase.paid_at,
        created_at=purchase.created_at,
    )


@router.get("/plans", response_model=list[PurchasablePlanOut])
def list_plans(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> list[PurchasablePlanOut]:
    _workspace, _membership = pair
    return [_plan_out(plan) for plan in BillingService(db).list_purchasable_plans()]


@router.get("/credit-packs", response_model=list[CreditPackOut])
def list_credit_packs(
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> list[CreditPackOut]:
    _workspace, _membership = pair
    return [_pack_out(pack) for pack in BillingService(db).list_active_credit_packs()]


@router.post("/checkout/subscription", response_model=CheckoutOut)
def checkout_subscription(
    body: SubscriptionCheckoutRequest,
    request: Request,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    workspace, _membership = pair
    purchase, _token = BillingService(db).create_subscription_checkout(
        workspace,
        user,
        body.plan_id,
        customer_ip=client_ip(request),
    )
    db.commit()
    return _checkout_out(purchase)


@router.post("/checkout/credit-packs", response_model=CheckoutOut)
def checkout_credit_pack(
    body: CreditPackCheckoutRequest,
    request: Request,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    workspace, _membership = pair
    purchase, _token = BillingService(db).create_credit_pack_checkout(
        workspace,
        user,
        body.credit_pack_id,
        customer_ip=client_ip(request),
    )
    db.commit()
    return _checkout_out(purchase)


@router.get("/purchases/{purchase_id}", response_model=PurchaseOut)
def get_purchase(
    purchase_id: uuid.UUID,
    pair: tuple[Workspace, WorkspaceMembership] = Depends(require_workspace),
    db: Session = Depends(get_db),
) -> PurchaseOut:
    workspace, _membership = pair
    purchase = BillingService(db).get_purchase_for_workspace(workspace, purchase_id)
    return _purchase_out(purchase)


@router.api_route(
    "/return/{gateway_code}/{purchase_id}",
    methods=["GET", "POST"],
    response_model=PurchaseOut,
)
def billing_return(
    gateway_code: str,
    purchase_id: uuid.UUID,
    db: Session = Depends(get_db),
    rt: str = Query(default="", alias="rt"),
) -> PurchaseOut:
    """Browser return from the hosted payment page.

    Query/body fields from the provider are ignored. Verification is a
    server-to-server transaction query using the stored tran_ref.
    """
    purchase = BillingService(db).complete_on_return(
        purchase_id,
        return_token=rt,
        gateway_code=gateway_code,
    )
    db.commit()
    return _purchase_out(purchase)
