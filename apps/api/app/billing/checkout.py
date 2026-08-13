"""Provider-independent checkout and fulfillment (Phase 6A)."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode, urljoin

from sqlalchemy.orm import Session

from app.billing.gateways.dtos import (
    CheckoutRequest,
    CustomerDetails,
    GatewayTransactionStatus,
)
from app.billing.gateways.registry import EnabledGateway, GatewayRegistry
from app.billing.models import (
    CreditPack,
    Plan,
    PlanStatus,
    Purchase,
    PurchaseKind,
    PurchaseStatus,
)
from app.billing.money import money_equal, normalize_currency, quantize_money
from app.billing.repository import (
    CreditPackRepository,
    PaymentGatewayConfigRepository,
    PlanRepository,
    PurchaseRepository,
)
from app.billing.service import SubscriptionService
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory
from app.identity.models import User
from app.usage.credits import CreditService
from app.usage.metrics import CreditLedgerEntryType
from app.workspaces.models import Workspace, WorkspaceKind

logger = logging.getLogger(__name__)

GRANT_REQUEST_ID_PREFIX = "purchase:"
DEFAULT_PHONE = "0500000000"


def hash_return_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def purchase_grant_request_id(purchase_id: uuid.UUID) -> str:
    return f"{GRANT_REQUEST_ID_PREFIX}{purchase_id}"


class BillingService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        registry: GatewayRegistry | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.registry = registry or GatewayRegistry(db, self.settings)
        self.purchases = PurchaseRepository(db)
        self.plans = PlanRepository(db)
        self.packs = CreditPackRepository(db)
        self.gateways = PaymentGatewayConfigRepository(db)
        self.subscriptions = SubscriptionService(db, self.settings)
        self.credits = CreditService(db, self.settings)

    def list_purchasable_plans(self) -> list[Plan]:
        return self.plans.list_purchasable()

    def list_active_credit_packs(self) -> list[CreditPack]:
        return self.packs.list_active()

    def create_subscription_checkout(
        self,
        workspace: Workspace,
        user: User,
        plan_id: uuid.UUID,
        *,
        customer_ip: str | None = None,
        spa_origin: str | None = None,
    ) -> tuple[Purchase, str]:
        self._assert_tenant_workspace(workspace)
        plan = self.plans.get_by_id(plan_id)
        if (
            plan is None
            or plan.status != PlanStatus.ACTIVE.value
            or plan.price_amount is None
        ):
            raise AppError(ErrorCategory.PLAN_UNAVAILABLE, "Plan is not available for purchase.")
        amount = quantize_money(plan.price_amount)
        currency = normalize_currency(plan.currency or self.settings.billing_currency)
        payload = {
            "kind": PurchaseKind.SUBSCRIPTION.value,
            "plan_id": str(plan.id),
            "plan_code": plan.code,
            "plan_name": plan.name,
            "amount": str(amount),
            "currency": currency,
        }
        description = f"Geem subscription: {plan.name}"
        return self._start_checkout(
            workspace,
            user,
            kind=PurchaseKind.SUBSCRIPTION,
            amount=amount,
            currency=currency,
            payload=payload,
            description=description,
            customer_ip=customer_ip,
            spa_origin=spa_origin,
        )

    def create_credit_pack_checkout(
        self,
        workspace: Workspace,
        user: User,
        credit_pack_id: uuid.UUID,
        *,
        customer_ip: str | None = None,
        spa_origin: str | None = None,
    ) -> tuple[Purchase, str]:
        self._assert_tenant_workspace(workspace)
        pack = self.packs.get_by_id(credit_pack_id)
        if pack is None or not pack.active:
            raise AppError(
                ErrorCategory.CREDIT_PACK_UNAVAILABLE,
                "Credit pack is not available for purchase.",
            )
        amount = quantize_money(pack.price_amount)
        currency = normalize_currency(pack.currency or self.settings.billing_currency)
        payload = {
            "kind": PurchaseKind.CREDIT_PACK.value,
            "credit_pack_id": str(pack.id),
            "credit_pack_code": pack.code,
            "credit_pack_name": pack.name,
            "credits": int(pack.credits),
            "amount": str(amount),
            "currency": currency,
        }
        description = f"Geem credit pack: {pack.name}"
        return self._start_checkout(
            workspace,
            user,
            kind=PurchaseKind.CREDIT_PACK,
            amount=amount,
            currency=currency,
            payload=payload,
            description=description,
            customer_ip=customer_ip,
            spa_origin=spa_origin,
        )

    def get_purchase_for_workspace(
        self, workspace: Workspace, purchase_id: uuid.UUID
    ) -> Purchase:
        purchase = self.purchases.get_for_workspace(workspace.id, purchase_id)
        if purchase is None:
            raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")
        return purchase

    def list_purchases_for_workspace(
        self,
        workspace: Workspace,
        *,
        limit: int = 25,
        offset: int = 0,
        status: str | None = None,
        kind: str | None = None,
    ) -> tuple[list[Purchase], int]:
        statuses: list[str] | None = None
        if status:
            allowed = {item.value for item in PurchaseStatus}
            if status not in allowed:
                raise AppError(ErrorCategory.VALIDATION, "Unknown purchase status filter.")
            # Hosted checkout sits in redirected until return; Workspace UI labels it Pending.
            if status == PurchaseStatus.PENDING.value:
                statuses = [PurchaseStatus.PENDING.value, PurchaseStatus.REDIRECTED.value]
            else:
                statuses = [status]
        if kind and kind not in {item.value for item in PurchaseKind}:
            raise AppError(ErrorCategory.VALIDATION, "Unknown purchase kind filter.")
        return self.purchases.list_for_workspace(
            workspace.id,
            limit=limit,
            offset=offset,
            statuses=statuses,
            kind=kind,
        )

    def complete_on_return(
        self,
        purchase_id: uuid.UUID,
        *,
        return_token: str,
        gateway_code: str | None = None,
    ) -> Purchase:
        """Verify via server-side gateway query, then fulfill at most once."""
        peek = self.purchases.get_by_id(purchase_id)
        if peek is None or not _token_matches(peek.return_token_hash, return_token):
            raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")
        if gateway_code:
            peek_config = self.gateways.get_by_id(peek.payment_gateway_config_id)
            if peek_config is None or gateway_code != peek_config.code:
                raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")

        purchase = self.purchases.get_by_id_for_update(purchase_id)
        if purchase is None or not _token_matches(purchase.return_token_hash, return_token):
            raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")

        config = self.gateways.get_by_id(purchase.payment_gateway_config_id)
        if config is None:
            raise AppError(
                ErrorCategory.PAYMENT_VERIFICATION_FAILED,
                "Purchase payment gateway is no longer available.",
            )
        if gateway_code and gateway_code != config.code:
            raise AppError(ErrorCategory.PURCHASE_NOT_FOUND, "Purchase not found.")

        if purchase.status == PurchaseStatus.PAID.value:
            return purchase

        if not purchase.provider_transaction_ref:
            raise AppError(
                ErrorCategory.PAYMENT_VERIFICATION_FAILED,
                "Purchase has no provider transaction to verify.",
            )

        adapter = self.registry.build_adapter(config.code)
        if not adapter.allowed_in_environment(self.settings):
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "The payment gateway cannot be used in this environment.",
            )
        credentials = self.registry.credentials_for(adapter, config)
        result = adapter.query_transaction(purchase.provider_transaction_ref, credentials)

        if result.status != GatewayTransactionStatus.PAID:
            purchase.status = _purchase_status_for_gateway(result.status)
            purchase.extra = {
                **(purchase.extra or {}),
                "last_query_status": result.status.value,
                "provider_status": (result.extra or {}).get("provider_status"),
            }
            self.db.flush()
            return purchase

        if result.amount is not None and not money_equal(result.amount, purchase.amount):
            return self._mark_failed(purchase, failure="amount_mismatch")
        if result.currency is not None and result.currency.upper() != purchase.currency.upper():
            return self._mark_failed(purchase, failure="currency_mismatch")

        self._fulfill(purchase)
        purchase.status = PurchaseStatus.PAID.value
        purchase.paid_at = datetime.now(timezone.utc)
        purchase.extra = {
            **(purchase.extra or {}),
            "last_query_status": result.status.value,
            "provider_status": (result.extra or {}).get("provider_status"),
        }
        self.db.flush()
        logger.info(
            "billing_purchase_paid",
            extra={
                "purchase_id": str(purchase.id),
                "workspace_id": str(purchase.workspace_id),
                "kind": purchase.kind,
            },
        )
        return purchase

    def _start_checkout(
        self,
        workspace: Workspace,
        user: User,
        *,
        kind: PurchaseKind,
        amount: Decimal,
        currency: str,
        payload: dict[str, Any],
        description: str,
        customer_ip: str | None,
        spa_origin: str | None = None,
    ) -> tuple[Purchase, str]:
        enabled = self._require_enabled_gateway()
        raw_token = secrets.token_urlsafe(32)
        cart_id = str(uuid.uuid4())
        extra: dict[str, Any] = {"gateway_code": enabled.code}
        origin = (spa_origin or "").strip().rstrip("/")
        if origin and self.settings.is_allowed_spa_origin(origin):
            extra["spa_origin"] = origin
        purchase = Purchase(
            workspace_id=workspace.id,
            actor_id=user.id,
            kind=kind.value,
            status=PurchaseStatus.PENDING.value,
            amount=amount,
            currency=currency,
            payment_gateway_config_id=enabled.config.id,
            cart_id=cart_id,
            return_token_hash=hash_return_token(raw_token),
            payload=payload,
            extra=extra,
        )
        self.purchases.create(purchase)
        return_url = self._return_url(enabled.code, purchase.id, raw_token)
        checkout = enabled.adapter.create_checkout(
            CheckoutRequest(
                purchase_id=purchase.id,
                cart_id=cart_id,
                amount=amount,
                currency=currency,
                description=description,
                customer=_customer_from_user(user, customer_ip),
                return_url=return_url,
            ),
            enabled.credentials,
        )
        purchase.provider_transaction_ref = checkout.provider_transaction_ref
        purchase.redirect_url = checkout.redirect_url
        purchase.status = PurchaseStatus.REDIRECTED.value
        self.db.flush()
        logger.info(
            "billing_checkout_created",
            extra={
                "purchase_id": str(purchase.id),
                "workspace_id": str(workspace.id),
                "kind": kind.value,
            },
        )
        return purchase, raw_token

    def _fulfill(self, purchase: Purchase) -> None:
        payload = purchase.payload or {}
        kind = payload.get("kind") or purchase.kind
        if kind == PurchaseKind.CREDIT_PACK.value:
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
            return
        if kind == PurchaseKind.SUBSCRIPTION.value:
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
            return
        raise AppError(ErrorCategory.INVALID_PURCHASE, "Unknown purchase kind.")

    def _mark_failed(self, purchase: Purchase, *, failure: str) -> Purchase:
        """Terminal failure that the caller must commit (do not raise after flush)."""
        purchase.status = PurchaseStatus.FAILED.value
        purchase.extra = {**(purchase.extra or {}), "failure": failure}
        self.db.flush()
        return purchase

    def _require_enabled_gateway(self) -> EnabledGateway:
        return self.registry.get_enabled()

    def _assert_tenant_workspace(self, workspace: Workspace) -> None:
        if workspace.kind == WorkspaceKind.SYSTEM.value:
            raise AppError(
                ErrorCategory.SYSTEM_WORKSPACE_CHECKOUT_FORBIDDEN,
                "System workspaces cannot checkout.",
            )

    def _return_url(self, gateway_code: str, purchase_id: uuid.UUID, raw_token: str) -> str:
        base = self.settings.app_url.rstrip("/") + "/"
        path = f"api/billing/return/{gateway_code}/{purchase_id}"
        return urljoin(base, path) + "?" + urlencode({"rt": raw_token})


def _customer_from_user(user: User, customer_ip: str | None) -> CustomerDetails:
    local = (user.email or "customer").split("@", 1)[0].replace(".", " ").strip()
    name = local.title() if local else "Geem Customer"
    return CustomerDetails(
        name=name,
        email=user.email,
        phone=DEFAULT_PHONE,
        ip=customer_ip,
    )


def _token_matches(stored_hash: str, raw: str) -> bool:
    if not raw or not stored_hash:
        return False
    digest = hash_return_token(raw)
    if len(digest) != len(stored_hash):
        return False
    return secrets.compare_digest(digest, stored_hash)


def _purchase_status_for_gateway(status: GatewayTransactionStatus) -> str:
    if status == GatewayTransactionStatus.CANCELLED:
        return PurchaseStatus.CANCELLED.value
    if status == GatewayTransactionStatus.EXPIRED:
        return PurchaseStatus.EXPIRED.value
    if status == GatewayTransactionStatus.PENDING:
        return PurchaseStatus.REDIRECTED.value
    return PurchaseStatus.FAILED.value
