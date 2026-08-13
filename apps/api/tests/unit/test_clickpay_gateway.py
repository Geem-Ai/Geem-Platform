"""Phase 6A — ClickPay adapter mapping (HTTP mocked; no live provider)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import pytest
import respx

from app.billing.gateways.clickpay import ClickPayGateway
from app.billing.gateways.dtos import (
    CheckoutRequest,
    CustomerDetails,
    GatewayCredentials,
    GatewayTransactionStatus,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory

BASE = "https://secure.clickpay.com.sa"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        jwt_secret="test-jwt-secret-not-for-production",
        clickpay_base_url=BASE,
        clickpay_timeout_seconds=5,
    )


def _creds(**extra: str) -> GatewayCredentials:
    values = {
        "profile_id": "59020",
        "server_key": "server-key-secret",
        "base_url": BASE,
    }
    values.update(extra)
    return GatewayCredentials(code="clickpay", values=values, test_mode=True)


def _checkout_request() -> CheckoutRequest:
    return CheckoutRequest(
        purchase_id=uuid.uuid4(),
        cart_id=str(uuid.uuid4()),
        amount=Decimal("49.00"),
        currency="SAR",
        description="Geem subscription: Pro",
        customer=CustomerDetails(
            name="Ada Lovelace",
            email="ada@example.com",
            phone="0501234567",
            ip="203.0.113.9",
        ),
        return_url="https://api.example/api/billing/return/clickpay/x?rt=tok",
    )


@respx.mock
def test_create_checkout_maps_hosted_page_fields() -> None:
    route = respx.post(f"{BASE}/payment/request").mock(
        return_value=httpx.Response(
            200,
            json={
                "tran_ref": "TST2214201508699",
                "redirect_url": "https://secure.clickpay.com.sa/payment/page/abc",
                "cart_id": "ignored",
            },
        )
    )
    result = ClickPayGateway(_settings()).create_checkout(_checkout_request(), _creds())
    assert result.provider_transaction_ref == "TST2214201508699"
    assert result.redirect_url == "https://secure.clickpay.com.sa/payment/page/abc"
    request = route.calls.last.request
    assert request.headers["authorization"] == "server-key-secret"
    assert "Bearer" not in request.headers["authorization"]
    body = request.read()
    import json

    payload = json.loads(body)
    assert payload["profile_id"] == 59020
    assert payload["tran_type"] == "sale"
    assert payload["tran_class"] == "ecom"
    assert payload["cart_currency"] == "SAR"
    assert payload["cart_amount"] == 49.0
    assert payload["hide_shipping"] is True
    assert "callback" not in payload
    assert payload["customer_details"]["email"] == "ada@example.com"


@respx.mock
def test_create_checkout_incomplete_response() -> None:
    respx.post(f"{BASE}/payment/request").mock(
        return_value=httpx.Response(200, json={"tran_ref": "TST1"})
    )
    with pytest.raises(AppError) as exc:
        ClickPayGateway(_settings()).create_checkout(_checkout_request(), _creds())
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_ERROR


@respx.mock
def test_create_checkout_network_error() -> None:
    respx.post(f"{BASE}/payment/request").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(AppError) as exc:
        ClickPayGateway(_settings()).create_checkout(_checkout_request(), _creds())
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_ERROR


@respx.mock
def test_create_checkout_http_error() -> None:
    respx.post(f"{BASE}/payment/request").mock(
        return_value=httpx.Response(401, json={"message": "bad key"})
    )
    with pytest.raises(AppError) as exc:
        ClickPayGateway(_settings()).create_checkout(_checkout_request(), _creds())
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_ERROR
    assert "server-key-secret" not in str(exc.value)


@respx.mock
def test_query_authorized_maps_to_paid() -> None:
    respx.post(f"{BASE}/payment/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "tran_ref": "TST2214201508699",
                "cart_amount": "49.00",
                "cart_currency": "SAR",
                "payment_result": {
                    "response_status": "A",
                    "response_message": "Authorised",
                },
            },
        )
    )
    result = ClickPayGateway(_settings()).query_transaction("TST2214201508699", _creds())
    assert result.status == GatewayTransactionStatus.PAID
    assert result.amount == Decimal("49.00")
    assert result.currency == "SAR"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("D", GatewayTransactionStatus.FAILED),
        ("E", GatewayTransactionStatus.FAILED),
        ("C", GatewayTransactionStatus.CANCELLED),
        ("X", GatewayTransactionStatus.EXPIRED),
        ("P", GatewayTransactionStatus.PENDING),
    ],
)
@respx.mock
def test_query_status_mapping(code: str, expected: GatewayTransactionStatus) -> None:
    respx.post(f"{BASE}/payment/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "tran_ref": "TST1",
                "cart_amount": "49.00",
                "cart_currency": "SAR",
                "payment_result": {"response_status": code},
            },
        )
    )
    result = ClickPayGateway(_settings()).query_transaction("TST1", _creds())
    assert result.status == expected


@respx.mock
def test_query_malformed_response() -> None:
    respx.post(f"{BASE}/payment/query").mock(
        return_value=httpx.Response(200, json={"tran_ref": "TST1"})
    )
    with pytest.raises(AppError) as exc:
        ClickPayGateway(_settings()).query_transaction("TST1", _creds())
    assert exc.value.category == ErrorCategory.PAYMENT_VERIFICATION_FAILED


@respx.mock
def test_query_network_error() -> None:
    respx.post(f"{BASE}/payment/query").mock(side_effect=httpx.TimeoutException("t"))
    with pytest.raises(AppError) as exc:
        ClickPayGateway(_settings()).query_transaction("TST1", _creds())
    assert exc.value.category == ErrorCategory.PAYMENT_VERIFICATION_FAILED


def test_missing_credentials() -> None:
    with pytest.raises(AppError) as exc:
        ClickPayGateway(_settings()).create_checkout(
            _checkout_request(),
            GatewayCredentials(code="clickpay", values={}, test_mode=True),
        )
    assert exc.value.category == ErrorCategory.BILLING_GATEWAY_UNAVAILABLE


def test_credentials_repr_hides_server_key() -> None:
    creds = _creds()
    text = repr(creds)
    assert "server-key-secret" not in text
    assert "clickpay" in text
