"""Purchase fulfillment dispatch — keeps BillingService._fulfill lean (Phase 9B)."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.orm import Session

from app.billing.models import Purchase, PurchaseKind
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.usage.credits import CreditService
from app.usage.metrics import CreditLedgerEntryType


GRANT_REQUEST_ID_PREFIX = "purchase:"


def purchase_grant_request_id(purchase_id: uuid.UUID) -> str:
    return f"{GRANT_REQUEST_ID_PREFIX}{purchase_id}"


class PurchaseFulfiller(Protocol):
    def fulfill(self, purchase: Purchase) -> None: ...


class CreditPackFulfillment:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.credits = CreditService(db, settings or get_settings())

    def fulfill(self, purchase: Purchase) -> None:
        payload = purchase.payload or {}
        credits = int(payload.get("credits") or 0)
        if credits <= 0:
            raise AppError(
                ErrorCategory.INVALID_PURCHASE,
                "Purchase snapshot is missing granted credits.",
            )
        self.credits.append(
            purchase.workspace_id,
            entry_type=CreditLedgerEntryType.GRANT,
            amount=credits,
            request_id=purchase_grant_request_id(purchase.id),
            source_type="purchase",
            source_id=str(purchase.id),
            extra={"kind": PurchaseKind.CREDIT_PACK.value},
        )


class WorkspaceSubscriptionFulfillment:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        from app.billing.service import SubscriptionService

        self.subscriptions = SubscriptionService(db, settings or get_settings())

    def fulfill(self, purchase: Purchase) -> None:
        payload = purchase.payload or {}
        raw_plan_id = payload.get("plan_id")
        try:
            plan_id = uuid.UUID(str(raw_plan_id))
        except (TypeError, ValueError) as exc:
            raise AppError(
                ErrorCategory.INVALID_PURCHASE,
                "Purchase snapshot is missing the target plan.",
            ) from exc
        self.subscriptions.assign_plan(
            purchase.workspace_id,
            plan_id,
            extra={
                "source": "purchase",
                "purchase_id": str(purchase.id),
            },
            require_active=False,
        )


class AppPurchaseFulfillment:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        from app.apps_catalog.commerce import AppCommerceService

        # fulfill-only — avoid BillingService ↔ AppCommerce init cycle
        self.commerce = AppCommerceService(db, settings, billing=False)

    def fulfill(self, purchase: Purchase) -> None:
        self.commerce.fulfill_purchase(purchase)


class PurchaseFulfillmentService:
    """Registry dispatch by purchase kind."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self._handlers: dict[str, PurchaseFulfiller] | None = None

    def _registry(self) -> dict[str, PurchaseFulfiller]:
        if self._handlers is None:
            cfg = self.settings
            self._handlers = {
                PurchaseKind.CREDIT_PACK.value: CreditPackFulfillment(self.db, cfg),
                PurchaseKind.SUBSCRIPTION.value: WorkspaceSubscriptionFulfillment(
                    self.db, cfg
                ),
                PurchaseKind.APP_ONE_TIME.value: AppPurchaseFulfillment(self.db, cfg),
                PurchaseKind.APP_SUBSCRIPTION.value: AppPurchaseFulfillment(
                    self.db, cfg
                ),
                PurchaseKind.APP_SUBSCRIPTION_RENEWAL.value: AppPurchaseFulfillment(
                    self.db, cfg
                ),
            }
        return self._handlers

    def fulfill(self, purchase: Purchase) -> None:
        payload = purchase.payload or {}
        kind = payload.get("kind") or purchase.kind
        handler = self._registry().get(str(kind))
        if handler is None:
            raise AppError(ErrorCategory.INVALID_PURCHASE, "Unknown purchase kind.")
        handler.fulfill(purchase)
