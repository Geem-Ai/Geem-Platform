"""ClickPay hosted-page adapter.

Creates a sale via POST /payment/request and verifies via POST /payment/query.
ClickPay redirects the browser to ``return``. ``callback`` is null so the
IPN POST does not race that browser hit.
Neither payload is payment proof — Geem always queries ``tran_ref``.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.billing.gateways.dtos import (
    CheckoutRequest,
    CheckoutResult,
    GatewayCredentials,
    GatewayTransactionStatus,
    TransactionQueryResult,
)
from app.billing.money import format_money, parse_decimal_money, require_sar
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

CLICKPAY_CODE = "clickpay"
DEFAULT_BASE_URL = "https://secure.clickpay.com.sa"

# ClickPay / PayTabs payment_result.response_status
_STATUS_MAP: dict[str, GatewayTransactionStatus] = {
    "A": GatewayTransactionStatus.PAID,
    "D": GatewayTransactionStatus.FAILED,
    "E": GatewayTransactionStatus.FAILED,
    "C": GatewayTransactionStatus.CANCELLED,
    "V": GatewayTransactionStatus.CANCELLED,
    "X": GatewayTransactionStatus.EXPIRED,
    "H": GatewayTransactionStatus.PENDING,
    "P": GatewayTransactionStatus.PENDING,
}


class ClickPayGateway:
    code = CLICKPAY_CODE

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._http_client = http_client

    def allowed_in_environment(self, settings: Settings) -> bool:
        del settings
        return True

    def credentials_from_stored(
        self,
        stored: dict[str, Any],
        settings: Settings,
        *,
        test_mode: bool,
    ) -> GatewayCredentials:
        profile_id = str(stored.get("profile_id") or settings.clickpay_profile_id or "").strip()
        server_key = str(stored.get("server_key") or settings.clickpay_server_key or "").strip()
        mode = stored.get("test_mode")
        resolved_test = test_mode if mode is None else bool(mode)
        if mode is None:
            resolved_test = bool(settings.clickpay_test_mode) if not stored else test_mode
        base_url = str(
            stored.get("base_url") or settings.clickpay_base_url or DEFAULT_BASE_URL
        ).rstrip("/")
        return GatewayCredentials(
            code=self.code,
            values={
                "profile_id": profile_id,
                "server_key": server_key,
                "base_url": base_url,
            },
            test_mode=resolved_test,
        )

    def create_checkout(
        self,
        request: CheckoutRequest,
        credentials: GatewayCredentials,
    ) -> CheckoutResult:
        profile_id, server_key, base_url = self._require_credentials(credentials)
        payload = {
            "profile_id": _as_profile_id(profile_id),
            "tran_type": "sale",
            "tran_class": "ecom",
            "cart_id": request.cart_id,
            "cart_description": request.description,
            "cart_currency": require_sar(request.currency),
            "cart_amount": format_money(request.amount),
            "hide_shipping": True,
            "callback": None,
            "return": request.return_url,
            "customer_details": _customer_payload(request),
        }
        body = self._post_json(
            f"{base_url}/payment/request",
            server_key=server_key,
            json_body=payload,
            error_category=ErrorCategory.BILLING_GATEWAY_ERROR,
            action="create_checkout",
        )
        tran_ref = str(body.get("tran_ref") or "").strip()
        redirect_url = str(body.get("redirect_url") or "").strip()
        if not tran_ref or not redirect_url:
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_ERROR,
                "Payment gateway returned an incomplete checkout response.",
            )
        logger.info(
            "clickpay_checkout_created",
            extra={
                "provider": "clickpay",
                "purchase_id": str(request.purchase_id),
                "cart_id": request.cart_id,
            },
        )
        return CheckoutResult(
            provider_transaction_ref=tran_ref,
            redirect_url=redirect_url,
            extra={"cart_id": body.get("cart_id")},
        )

    def query_transaction(
        self,
        provider_transaction_ref: str,
        credentials: GatewayCredentials,
    ) -> TransactionQueryResult:
        profile_id, server_key, base_url = self._require_credentials(credentials)
        ref = (provider_transaction_ref or "").strip()
        if not ref:
            raise AppError(
                ErrorCategory.PAYMENT_VERIFICATION_FAILED,
                "Missing provider transaction reference.",
            )
        body = self._post_json(
            f"{base_url}/payment/query",
            server_key=server_key,
            json_body={
                "profile_id": _as_profile_id(profile_id),
                "tran_ref": ref,
            },
            error_category=ErrorCategory.PAYMENT_VERIFICATION_FAILED,
            action="query_transaction",
        )
        return self._parse_query_result(ref, body)

    def _parse_query_result(
        self,
        requested_ref: str,
        body: dict[str, Any],
    ) -> TransactionQueryResult:
        payment_result = body.get("payment_result")
        if not isinstance(payment_result, dict):
            payment_result = {}
        raw_status = str(
            payment_result.get("response_status") or body.get("response_status") or ""
        ).strip().upper()
        if not raw_status:
            raise AppError(
                ErrorCategory.PAYMENT_VERIFICATION_FAILED,
                "Payment gateway returned a malformed transaction status.",
            )
        status = _STATUS_MAP.get(raw_status, GatewayTransactionStatus.FAILED)
        amount = _optional_money(body.get("cart_amount"))
        currency = None
        raw_currency = body.get("cart_currency")
        if isinstance(raw_currency, str) and raw_currency.strip():
            currency = raw_currency.strip().upper()
        tran_ref = str(body.get("tran_ref") or requested_ref).strip() or requested_ref
        return TransactionQueryResult(
            provider_transaction_ref=tran_ref,
            status=status,
            amount=amount,
            currency=currency,
            extra={
                "provider_status": raw_status,
                "provider_message": payment_result.get("response_message"),
            },
        )

    def _require_credentials(
        self, credentials: GatewayCredentials
    ) -> tuple[str, str, str]:
        profile_id = str(credentials.get("profile_id") or "").strip()
        server_key = str(credentials.get("server_key") or "").strip()
        base_url = str(credentials.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        if not profile_id or not server_key:
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "Payment gateway credentials are not configured.",
            )
        return profile_id, server_key, base_url

    def _post_json(
        self,
        url: str,
        *,
        server_key: str,
        json_body: dict[str, Any],
        error_category: ErrorCategory,
        action: str,
    ) -> dict[str, Any]:
        timeout = float(self.settings.clickpay_timeout_seconds or 30.0)
        headers = {
            "authorization": server_key,
            "content-type": "application/json",
            "accept": "application/json",
        }
        try:
            if self._http_client is not None:
                response = self._http_client.post(
                    url, headers=headers, json=json_body, timeout=timeout
                )
            else:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(url, headers=headers, json=json_body)
        except httpx.TimeoutException as exc:
            logger.warning("clickpay_timeout", extra={"provider": "clickpay", "action": action})
            raise AppError(
                error_category,
                "Payment gateway request timed out.",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "clickpay_http_error",
                extra={"provider": "clickpay", "action": action},
            )
            raise AppError(
                error_category,
                "Payment gateway is unreachable.",
                retryable=True,
            ) from exc

        if response.status_code >= 400:
            logger.warning(
                "clickpay_http_status",
                extra={
                    "provider": "clickpay",
                    "action": action,
                    "status": response.status_code,
                },
            )
            raise AppError(
                error_category,
                "Payment gateway rejected the request.",
                details={"status": response.status_code},
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise AppError(
                error_category,
                "Payment gateway returned a malformed response.",
            ) from exc
        if not isinstance(body, dict):
            raise AppError(
                error_category,
                "Payment gateway returned a malformed response.",
            )
        return body


def _as_profile_id(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def _customer_payload(request: CheckoutRequest) -> dict[str, str]:
    customer = request.customer
    phone = (customer.phone or "0500000000").strip() or "0500000000"
    return {
        "name": customer.name.strip() or "Geem Customer",
        "email": customer.email.strip(),
        "phone": phone,
        "street1": "N/A",
        "city": "Riyadh",
        "state": "RD",
        "country": "SA",
        "zip": "00000",
        "ip": (customer.ip or "127.0.0.1").strip() or "127.0.0.1",
    }


def _optional_money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return parse_decimal_money(value)
    except (AppError, InvalidOperation, TypeError, ValueError):
        return None
