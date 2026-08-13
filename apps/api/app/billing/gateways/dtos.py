"""Provider-neutral billing gateway DTOs."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class GatewayTransactionStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class CustomerDetails:
    name: str
    email: str
    phone: str | None = None
    ip: str | None = None


@dataclass(frozen=True)
class CheckoutRequest:
    purchase_id: uuid.UUID
    cart_id: str
    amount: Decimal
    currency: str
    description: str
    customer: CustomerDetails
    return_url: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckoutResult:
    provider_transaction_ref: str
    redirect_url: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransactionQueryResult:
    provider_transaction_ref: str
    status: GatewayTransactionStatus
    amount: Decimal | None = None
    currency: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayCredentials:
    """Adapter credentials. ``secret`` is never included in repr/logs."""

    code: str
    values: dict[str, Any] = field(default_factory=dict)
    test_mode: bool = True

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __repr__(self) -> str:
        return f"GatewayCredentials(code={self.code!r}, test_mode={self.test_mode})"
