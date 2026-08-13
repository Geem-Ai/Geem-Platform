"""Payment gateway adapters. Domain code talks only to BillingGateway."""

from app.billing.gateways.dtos import (
    CheckoutRequest,
    CheckoutResult,
    CustomerDetails,
    GatewayCredentials,
    GatewayTransactionStatus,
    TransactionQueryResult,
)
from app.billing.gateways.protocol import BillingGateway
from app.billing.gateways.registry import GatewayRegistry

__all__ = [
    "BillingGateway",
    "CheckoutRequest",
    "CheckoutResult",
    "CustomerDetails",
    "GatewayCredentials",
    "GatewayRegistry",
    "GatewayTransactionStatus",
    "TransactionQueryResult",
]
