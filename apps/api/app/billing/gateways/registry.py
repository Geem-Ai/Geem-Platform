"""Resolve the single enabled payment gateway. Never silently pick a fallback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.billing.gateways.clickpay import ClickPayGateway
from app.billing.gateways.dtos import GatewayCredentials
from app.billing.gateways.noop import NoopGateway
from app.billing.gateways.protocol import BillingGateway
from app.billing.models import PaymentGatewayConfig
from app.common.crypto import decrypt_json
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

AdapterFactory = Callable[..., BillingGateway]

_ADAPTERS: dict[str, AdapterFactory] = {
    NoopGateway.code: NoopGateway,
    ClickPayGateway.code: ClickPayGateway,
}


def registered_adapter_codes() -> frozenset[str]:
    return frozenset(_ADAPTERS.keys())


class EnabledGateway:
    def __init__(
        self,
        adapter: BillingGateway,
        config: PaymentGatewayConfig,
        credentials: GatewayCredentials,
    ) -> None:
        self.adapter = adapter
        self.config = config
        self.credentials = credentials

    @property
    def code(self) -> str:
        return self.adapter.code


class GatewayRegistry:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        adapters: dict[str, AdapterFactory] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.adapters = adapters if adapters is not None else dict(_ADAPTERS)

    def get_enabled(self) -> EnabledGateway:
        from app.billing.repository import PaymentGatewayConfigRepository

        rows = PaymentGatewayConfigRepository(self.db).list_enabled()
        if not rows:
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "No payment gateway is enabled.",
            )
        if len(rows) != 1:
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "Multiple payment gateways are enabled.",
            )
        config = rows[0]
        adapter = self.build_adapter(config.code)
        if not adapter.allowed_in_environment(self.settings):
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "The enabled payment gateway cannot be used in this environment.",
            )
        credentials = self.credentials_for(adapter, config)
        return EnabledGateway(adapter=adapter, config=config, credentials=credentials)

    def credentials_for(
        self, adapter: BillingGateway, config: PaymentGatewayConfig
    ) -> GatewayCredentials:
        stored = self.decrypt_stored(config)
        return adapter.credentials_from_stored(
            stored, self.settings, test_mode=config.test_mode
        )

    def build_adapter(self, code: str) -> BillingGateway:
        factory = self.adapters.get(code)
        if factory is None:
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "The enabled payment gateway adapter is not available.",
                details={"code": code},
            )
        return factory(settings=self.settings)

    def decrypt_stored(self, config: PaymentGatewayConfig) -> dict[str, Any]:
        raw = (config.credentials_encrypted or "").strip()
        if not raw:
            return {}
        try:
            return decrypt_json(raw, settings=self.settings)
        except (ValueError, TypeError):
            logger.warning(
                "gateway_credentials_decrypt_failed",
                extra={"gateway_config_id": str(config.id)},
            )
            raise AppError(
                ErrorCategory.BILLING_GATEWAY_UNAVAILABLE,
                "Payment gateway credentials could not be loaded.",
            )
