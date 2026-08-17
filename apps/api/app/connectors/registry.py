"""Provider-neutral connector adapter registry (Phase 9C)."""

from __future__ import annotations

from typing import Any

from app.connectors.adapters import ConnectorAdapter, ConnectorCapabilities
from app.connectors.types import ConnectorAuthMode, ConnectorKind
from app.core.errors import AppError, ErrorCategory


def _adapter_configured(adapter: ConnectorAdapter) -> bool:
    """True when the adapter has no config gate, or the gate passes."""
    check = getattr(adapter, "is_configured", None)
    if callable(check):
        return bool(check())
    if hasattr(adapter, "configured"):
        return bool(getattr(adapter, "configured"))
    return True


def _unavailable_reason(adapter: ConnectorAdapter, key: str) -> str | None:
    reason = getattr(adapter, "unavailable_reason", None)
    if callable(reason):
        value = reason()
        return str(value) if value else None
    if isinstance(reason, str) and reason:
        return reason
    return f"{key}_not_configured"


class ConnectorRegistry:
    """In-process adapter registry. Production providers register in 9D–9F."""

    def __init__(self) -> None:
        self._adapters: dict[str, ConnectorAdapter] = {}

    def register(self, adapter: ConnectorAdapter) -> None:
        key = getattr(adapter, "key", None)
        if not key or not isinstance(key, str):
            raise AppError(
                ErrorCategory.VALIDATION,
                "Connector adapter must declare a string key.",
            )
        if key in self._adapters:
            raise AppError(
                ErrorCategory.CONNECTOR_ALREADY_REGISTERED,
                f"Connector '{key}' is already registered.",
                details={"connector_key": key},
            )
        self._adapters[key] = adapter

    def unregister(self, key: str) -> None:
        self._adapters.pop(key, None)

    def clear(self) -> None:
        self._adapters.clear()

    def has(self, key: str) -> bool:
        return key in self._adapters

    def get(self, key: str) -> ConnectorAdapter:
        """Return the adapter even when not configured (introspection).

        Callers that need live operations must check ``is_available`` first.
        """
        adapter = self._adapters.get(key)
        if adapter is None:
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "Connector adapter is not available.",
                details={"connector_key": key},
            )
        return adapter

    def try_get(self, key: str) -> ConnectorAdapter | None:
        return self._adapters.get(key)

    def is_available(self, key: str | None) -> bool:
        if not key or key not in self._adapters:
            return False
        return _adapter_configured(self._adapters[key])

    def capabilities(self, key: str) -> ConnectorCapabilities | None:
        adapter = self._adapters.get(key)
        if adapter is None:
            return None
        return adapter.capabilities

    def describe(self, key: str | None) -> dict[str, Any] | None:
        """Public capability snapshot for App detail DTOs."""
        if not key:
            return None
        adapter = self._adapters.get(key)
        if adapter is None:
            return {
                "key": key,
                "kind": None,
                "available": False,
                "auth_mode": None,
                "can_connect": False,
                "supports_sync": False,
                "supports_webhooks": False,
                "supports_health_check": False,
                "unavailable_reason": None,
            }
        caps = adapter.capabilities
        available = _adapter_configured(adapter)
        payload: dict[str, Any] = {
            "key": adapter.key,
            "kind": adapter.kind.value
            if isinstance(adapter.kind, ConnectorKind)
            else str(adapter.kind),
            "available": available,
            "auth_mode": adapter.auth_mode.value
            if isinstance(adapter.auth_mode, ConnectorAuthMode)
            else str(adapter.auth_mode),
            "can_connect": available,
            "supports_sync": bool(caps.supports_sync),
            "supports_webhooks": bool(caps.supports_webhooks),
            "supports_health_check": bool(caps.supports_health_check),
        }
        if not available:
            payload["unavailable_reason"] = _unavailable_reason(adapter, key)
        return payload

    def keys(self) -> list[str]:
        return sorted(self._adapters.keys())


# Process-wide registry. Tests may clear/register fake adapters.
connector_registry = ConnectorRegistry()
