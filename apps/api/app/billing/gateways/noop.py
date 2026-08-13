"""Local/dev gateway: no money movement, same BillingService fulfillment path."""

from __future__ import annotations

import uuid
from typing import Any

from app.billing.gateways.dtos import (
    CheckoutRequest,
    CheckoutResult,
    GatewayCredentials,
    GatewayTransactionStatus,
    TransactionQueryResult,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


class NoopGateway:
    code = "noop"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def allowed_in_environment(self, settings: Settings) -> bool:
        return settings.is_local

    def credentials_from_stored(
        self,
        stored: dict[str, Any],
        settings: Settings,
        *,
        test_mode: bool,
    ) -> GatewayCredentials:
        del stored
        return GatewayCredentials(code=self.code, values={}, test_mode=test_mode)

    def create_checkout(
        self,
        request: CheckoutRequest,
        credentials: GatewayCredentials,
    ) -> CheckoutResult:
        self._assert_local(credentials)
        return CheckoutResult(
            provider_transaction_ref=f"noop_{request.purchase_id.hex}_{uuid.uuid4().hex[:12]}",
            redirect_url=request.return_url,
            extra={"simulated": True},
        )

    def query_transaction(
        self,
        provider_transaction_ref: str,
        credentials: GatewayCredentials,
    ) -> TransactionQueryResult:
        self._assert_local(credentials)
        if not provider_transaction_ref:
            raise AppError(
                ErrorCategory.PAYMENT_VERIFICATION_FAILED,
                "Missing provider transaction reference.",
            )
        return TransactionQueryResult(
            provider_transaction_ref=provider_transaction_ref,
            status=GatewayTransactionStatus.PAID,
            extra={"simulated": True},
        )

    def _assert_local(self, credentials: GatewayCredentials) -> None:
        del credentials
        from app.core.config import get_settings

        cfg = self.settings or get_settings()
        if not cfg.is_local:
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "The Noop payment gateway cannot be used outside local/test.",
            )
