"""OpenWA connector adapter registration + webhook verification."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.connectors.adapters import (
    ChannelConnectorAdapter,
    ConnectorCapabilities,
    HealthCheckResult,
    WebhookConnectorAdapter,
    WebhookHandleResult,
    WebhookRequestContext,
)
from app.connectors.providers.openwa.client import OpenWAClient
from app.connectors.providers.openwa.service import CONNECTOR_KEY, map_openwa_status
from app.connectors.providers.openwa.webhook import (
    HEADER_DELIVERY,
    HEADER_SIGNATURE,
    MESSAGE_EVENTS,
    SESSION_EVENTS,
    build_webhook_handle_result,
    extract_event_name,
    extract_idempotency_key,
    extract_session_status,
    normalize_message_received,
    parse_openwa_event,
    verify_openwa_signature,
)
from app.connectors.registry import connector_registry
from app.connectors.types import ConnectionHealth, ConnectorAuthMode, ConnectorKind
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCategory


@dataclass
class OpenWAConnector(ChannelConnectorAdapter, WebhookConnectorAdapter):
    key: str = CONNECTOR_KEY
    kind: ConnectorKind = ConnectorKind.CHANNEL
    auth_mode: ConnectorAuthMode = ConnectorAuthMode.CUSTOM
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            supports_oauth=False,
            supports_credentials=False,
            supports_sync=False,
            supports_webhooks=True,
            supports_health_check=True,
        )
    )
    settings: Settings | None = None
    client_factory: type[OpenWAClient] | None = None

    def _settings(self) -> Settings:
        return self.settings or get_settings()

    def _client(self) -> OpenWAClient:
        factory = self.client_factory or OpenWAClient
        return factory(settings=self._settings())

    def is_configured(self) -> bool:
        return self._settings().openwa_configured

    @property
    def unavailable_reason(self) -> str | None:
        if self.is_configured():
            return None
        return ErrorCategory.OPENWA_NOT_CONFIGURED.value

    def health_check(
        self,
        *,
        credentials: dict[str, Any],
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> HealthCheckResult:
        _ = connection_id, workspace_id
        session_id = str(credentials.get("session_id") or "").strip()
        if not session_id:
            return HealthCheckResult(
                health=ConnectionHealth.FAILED,
                error_code=ErrorCategory.CONNECTOR_CREDENTIALS_INVALID.value,
                error_message="Connection credentials are missing an OpenWA session id.",
            )
        with self._client() as client:
            try:
                session = client.get_session(session_id)
            except AppError as exc:
                if exc.category == ErrorCategory.OPENWA_SESSION_NOT_FOUND:
                    return HealthCheckResult(
                        health=ConnectionHealth.FAILED,
                        error_code=exc.category.value,
                        error_message=exc.message,
                    )
                if exc.category in {
                    ErrorCategory.OPENWA_TIMEOUT,
                    ErrorCategory.OPENWA_UNAVAILABLE,
                }:
                    return HealthCheckResult(
                        health=ConnectionHealth.DEGRADED,
                        error_code=exc.category.value,
                        error_message=exc.message,
                    )
                return HealthCheckResult(
                    health=ConnectionHealth.FAILED,
                    error_code=exc.category.value,
                    error_message=exc.message,
                )
        mapping = map_openwa_status(session.status)
        return HealthCheckResult(
            health=mapping.health,
            details={"provider_status": mapping.provider_status},
        )

    def disconnect(
        self,
        *,
        credentials: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
        sync_state: dict[str, Any] | None = None,
    ) -> None:
        _ = connection_id, workspace_id
        creds = dict(credentials or {})
        session_id = str(creds.get("session_id") or "").strip()
        if not session_id:
            return
        state = dict(sync_state or {})
        webhook_id = str(state.get("webhook_id") or "").strip()
        try:
            with self._client() as client:
                if webhook_id:
                    try:
                        client.delete_webhook(session_id, webhook_id)
                    except Exception:
                        pass
                try:
                    client.logout_session(session_id)
                except Exception:
                    pass
                try:
                    client.delete_session(session_id)
                except Exception:
                    pass
        except Exception:
            return

    def verify_and_handle_webhook(
        self,
        *,
        request: WebhookRequestContext,
        credentials: dict[str, Any] | None,
    ) -> WebhookHandleResult:
        creds = dict(credentials or {})
        secret = str(creds.get("webhook_secret") or "").strip()
        session_id = str(creds.get("session_id") or "").strip()
        if not secret or not session_id:
            return build_webhook_handle_result(
                accepted=False,
                idempotency_key=None,
                enqueue=False,
                error_code=ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED.value,
            )

        signature = request.headers.get(HEADER_SIGNATURE)
        if not verify_openwa_signature(
            raw_body=request.raw_body,
            signature=signature,
            secret=secret,
        ):
            return build_webhook_handle_result(
                accepted=False,
                idempotency_key=None,
                enqueue=False,
                error_code=ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED.value,
            )

        try:
            payload = parse_openwa_event(request.raw_body)
        except ValueError:
            return build_webhook_handle_result(
                accepted=False,
                idempotency_key=None,
                enqueue=False,
                error_code=ErrorCategory.CONNECTOR_WEBHOOK_INVALID.value,
            )

        event_name = extract_event_name(headers=request.headers, payload=payload)
        idempotency_key = extract_idempotency_key(
            headers=request.headers,
            payload=payload,
        )
        payload_session_id = _extract_session_id(payload)
        if payload_session_id and payload_session_id != session_id:
            return build_webhook_handle_result(
                accepted=False,
                idempotency_key=idempotency_key,
                enqueue=False,
                error_code=ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED.value,
            )

        delivery_id = request.headers.get(HEADER_DELIVERY)
        if event_name in MESSAGE_EVENTS:
            normalized = normalize_message_received(payload)
            if normalized is None:
                return build_webhook_handle_result(
                    accepted=True,
                    idempotency_key=idempotency_key,
                    enqueue=False,
                    ignore=True,
                    provider_event_id=delivery_id,
                )
            if normalized.from_me or not normalized.body.strip():
                return build_webhook_handle_result(
                    accepted=True,
                    idempotency_key=idempotency_key or normalized.provider_message_id,
                    enqueue=False,
                    ignore=True,
                    provider_event_id=normalized.provider_message_id,
                )
            return build_webhook_handle_result(
                accepted=True,
                idempotency_key=idempotency_key or normalized.provider_message_id,
                enqueue=True,
                enqueue_payload={
                    "kind": "openwa_message_received",
                    "provider_message_id": normalized.provider_message_id,
                    "external_chat_id": normalized.external_chat_id,
                    "sender_id": normalized.sender_id,
                    "body": normalized.body,
                    "message_type": normalized.message_type,
                    "provider_timestamp": normalized.provider_timestamp,
                    "is_group": normalized.is_group,
                    "has_media": normalized.has_media,
                    "chat_kind": normalized.chat_kind,
                },
                provider_event_id=normalized.provider_message_id,
            )

        if event_name in SESSION_EVENTS:
            provider_status, last_error = extract_session_status(payload)
            # Prefer provider idempotency key. Fallback must stay unique per delivery
            # so ready→disconnected→ready is not collapsed.
            fallback_key = (
                f"openwa:{request.connection_id}:{event_name}:"
                f"{provider_status or 'unknown'}:"
                f"{delivery_id or hashlib.sha256(request.raw_body).hexdigest()[:24]}"
            )
            return build_webhook_handle_result(
                accepted=True,
                idempotency_key=idempotency_key or fallback_key,
                enqueue=True,
                enqueue_payload={
                    "kind": "openwa_session_event",
                    "event": event_name,
                    "provider_status": provider_status,
                    "last_error": last_error,
                },
                provider_event_id=delivery_id or fallback_key,
            )

        return build_webhook_handle_result(
            accepted=True,
            idempotency_key=idempotency_key,
            enqueue=False,
            ignore=True,
            provider_event_id=delivery_id,
        )


def _extract_session_id(payload: dict[str, Any]) -> str | None:
    direct = payload.get("sessionId") or payload.get("session_id")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("sessionId") or data.get("session_id")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def register_openwa_connector(
    registry: Any | None = None,
    *,
    settings: Settings | None = None,
    client_factory: type[OpenWAClient] | None = None,
) -> OpenWAConnector:
    reg = registry or connector_registry
    adapter = OpenWAConnector(settings=settings, client_factory=client_factory)
    if reg.has(CONNECTOR_KEY):
        reg.unregister(CONNECTOR_KEY)
    reg.register(adapter)
    return adapter
