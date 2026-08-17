"""Provider-neutral connector adapter registry (Phase 9C)."""

from __future__ import annotations

from typing import Any

from app.connectors.adapters import ConnectorAdapter, ConnectorCapabilities
from app.connectors.types import ConnectorAuthMode, ConnectorKind
from app.core.errors import AppError, ErrorCategory


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
        return bool(key) and key in self._adapters

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
            }
        caps = adapter.capabilities
        return {
            "key": adapter.key,
            "kind": adapter.kind.value
            if isinstance(adapter.kind, ConnectorKind)
            else str(adapter.kind),
            "available": True,
            "auth_mode": adapter.auth_mode.value
            if isinstance(adapter.auth_mode, ConnectorAuthMode)
            else str(adapter.auth_mode),
            "can_connect": True,
            "supports_sync": bool(caps.supports_sync),
            "supports_webhooks": bool(caps.supports_webhooks),
            "supports_health_check": bool(caps.supports_health_check),
        }

    def keys(self) -> list[str]:
        return sorted(self._adapters.keys())


# Process-wide registry. Tests may clear/register fake adapters.
connector_registry = ConnectorRegistry()
