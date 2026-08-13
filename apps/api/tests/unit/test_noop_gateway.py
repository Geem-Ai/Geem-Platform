from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.billing.gateways.dtos import (
    CheckoutRequest,
    CustomerDetails,
    GatewayCredentials,
    GatewayTransactionStatus,
)
from app.billing.gateways.noop import NoopGateway
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory


def _request() -> CheckoutRequest:
    pid = uuid.uuid4()
    return CheckoutRequest(
        purchase_id=pid,
        cart_id=str(uuid.uuid4()),
        amount=Decimal("10.00"),
        currency="SAR",
        description="test",
        customer=CustomerDetails(name="T", email="t@example.com"),
        return_url=f"http://testserver/api/billing/return/noop/{pid}?rt=abc",
    )


def test_noop_create_and_query_paid_in_local() -> None:
    gw = NoopGateway(Settings(_env_file=None, app_env="test", jwt_secret="x" * 40))
    creds = GatewayCredentials(code="noop", values={}, test_mode=True)
    result = gw.create_checkout(_request(), creds)
    assert result.redirect_url.endswith("rt=abc")
    assert result.provider_transaction_ref.startswith("noop_")
    queried = gw.query_transaction(result.provider_transaction_ref, creds)
    assert queried.status == GatewayTransactionStatus.PAID
    assert queried.amount is None
    assert queried.currency is None


def test_noop_rejected_outside_local() -> None:
    gw = NoopGateway(
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="a" * 40,
            cors_origins="https://app.geem.ai",
        )
    )
    creds = GatewayCredentials(code="noop", values={}, test_mode=True)
    with pytest.raises(AppError) as exc:
        gw.create_checkout(_request(), creds)
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_UNAVAILABLE
    assert not gw.allowed_in_environment(
        Settings(_env_file=None, app_env="production", jwt_secret="a" * 40)
    )
