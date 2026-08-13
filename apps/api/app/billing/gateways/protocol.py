"""BillingGateway contract. Adding a provider must not change BillingService."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.billing.gateways.dtos import (
    CheckoutRequest,
    CheckoutResult,
    GatewayCredentials,
    TransactionQueryResult,
)
from app.core.config import Settings


@runtime_checkable
class BillingGateway(Protocol):
    @property
    def code(self) -> str: ...

    def allowed_in_environment(self, settings: Settings) -> bool: ...

    def credentials_from_stored(
        self,
        stored: dict[str, Any],
        settings: Settings,
        *,
        test_mode: bool,
    ) -> GatewayCredentials: ...

    def create_checkout(
        self,
        request: CheckoutRequest,
        credentials: GatewayCredentials,
    ) -> CheckoutResult: ...

    def query_transaction(
        self,
        provider_transaction_ref: str,
        credentials: GatewayCredentials,
    ) -> TransactionQueryResult: ...
