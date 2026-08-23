"""Per-adapter gateway configuration schema for Platform Admin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.billing.gateways.clickpay import CLICKPAY_CODE
from app.billing.gateways.noop import NoopGateway
from app.billing.gateways.registry import registered_adapter_codes
from app.core.errors import AppError, ErrorCategory

NOOP_CODE = NoopGateway.code

GATEWAY_DISPLAY_NAMES: dict[str, str] = {
    CLICKPAY_CODE: "ClickPay",
    NOOP_CODE: "Manual / Noop (local)",
}


@dataclass(frozen=True)
class CredentialFieldSchema:
    key: str
    label: str
    secret: bool
    required_on_create: bool = True


@dataclass(frozen=True)
class GatewayConfigSchema:
    code: str
    display_name: str
    credential_fields: tuple[CredentialFieldSchema, ...]
    supports_test_mode: bool = False

    def validate_create_payload(
        self,
        *,
        credentials: dict[str, Any] | None,
        test_mode: bool | None,
    ) -> dict[str, Any]:
        stored: dict[str, Any] = {}
        creds = credentials or {}
        for field in self.credential_fields:
            raw = creds.get(field.key)
            value = str(raw).strip() if raw is not None else ""
            if field.required_on_create and not value:
                raise AppError(
                    ErrorCategory.VALIDATION,
                    f"Gateway field '{field.key}' is required.",
                    details={"field": field.key},
                )
            if value:
                stored[field.key] = value
        return stored

    def merge_update_payload(
        self,
        existing: dict[str, Any],
        *,
        credentials: dict[str, Any] | None,
        test_mode: bool | None,
        clear_fields: set[str] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Return merged stored credentials and whether secrets were rotated."""
        merged = dict(existing or {})
        rotated = False
        if clear_fields:
            for key in clear_fields:
                if key in merged:
                    del merged[key]
                    rotated = True
        if credentials:
            for field in self.credential_fields:
                if field.key not in credentials:
                    continue
                raw = credentials[field.key]
                if raw is None:
                    continue
                value = str(raw).strip()
                if not value:
                    continue
                if field.secret and merged.get(field.key) != value:
                    rotated = True
                merged[field.key] = value
        return merged, rotated


_REGISTRY: dict[str, GatewayConfigSchema] = {
    CLICKPAY_CODE: GatewayConfigSchema(
        code=CLICKPAY_CODE,
        display_name=GATEWAY_DISPLAY_NAMES[CLICKPAY_CODE],
        supports_test_mode=True,
        credential_fields=(
            CredentialFieldSchema("profile_id", "Profile ID", secret=False),
            CredentialFieldSchema("server_key", "Server Key", secret=True),
        ),
    ),
    NOOP_CODE: GatewayConfigSchema(
        code=NOOP_CODE,
        display_name=GATEWAY_DISPLAY_NAMES[NOOP_CODE],
        supports_test_mode=True,
        credential_fields=(),
    ),
}


def _assert_registry_in_sync() -> None:
    adapter_codes = registered_adapter_codes()
    schema_codes = frozenset(_REGISTRY.keys())
    if adapter_codes != schema_codes:
        missing = sorted(adapter_codes - schema_codes)
        extra = sorted(schema_codes - adapter_codes)
        raise RuntimeError(
            "Gateway config schema out of sync with adapters: "
            f"missing_schemas={missing} extra_schemas={extra}"
        )


_assert_registry_in_sync()


def registered_gateway_codes() -> tuple[str, ...]:
    return tuple(sorted(registered_adapter_codes()))


def gateway_config_schema(code: str) -> GatewayConfigSchema:
    clean = code.strip().lower()
    schema = _REGISTRY.get(clean)
    if schema is None:
        raise AppError(
            ErrorCategory.VALIDATION,
            "Unknown payment gateway adapter.",
            details={"code": clean},
        )
    return schema


def gateway_display_name(code: str) -> str:
    return GATEWAY_DISPLAY_NAMES.get(code, code)


def identity_fields_for(code: str) -> frozenset[str]:
    """Stored credential keys that pin merchant identity for in-flight purchases."""
    if code == CLICKPAY_CODE:
        return frozenset({"profile_id", "test_mode", "base_url"})
    return frozenset()
