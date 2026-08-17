"""Connector adapter protocols (Phase 9C).

Narrow interfaces — providers implement only what they need.
Persistence, tenancy, encryption, and commercial access stay in Geem services.

Methods are synchronous to match Geem service/Celery conventions; providers
may wrap async SDKs internally when added in 9D–9F.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.connectors.types import ConnectorAuthMode, ConnectorKind, ConnectionHealth


@dataclass(frozen=True, slots=True)
class ConnectorCapabilities:
    supports_oauth: bool = False
    supports_credentials: bool = False
    supports_sync: bool = False
    supports_webhooks: bool = False
    supports_health_check: bool = True


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    health: ConnectionHealth
    error_code: str | None = None
    error_message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OAuthAuthorizationRequest:
    authorization_url: str
    state: str
    code_challenge: str | None = None
    code_challenge_method: str | None = None


@dataclass(frozen=True, slots=True)
class OAuthCompletionResult:
    credentials: dict[str, Any]
    external_account_id: str | None = None
    external_account_name: str | None = None
    credentials_expires_at: datetime | None = None
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class SyncResult:
    items_seen: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_failed: int = 0
    sync_state: dict[str, Any] | None = None
    partial: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class WebhookHandleResult:
    accepted: bool
    provider_event_id: str | None = None
    idempotency_key: str | None = None
    enqueue: bool = False
    enqueue_payload: dict[str, Any] = field(default_factory=dict)
    http_status: int = 200
    response_body: bytes | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    ignore: bool = False
    error_code: str | None = None


@dataclass(slots=True)
class WebhookRequestContext:
    """Raw inbound webhook material for provider verification."""

    connector_key: str
    workspace_id: uuid.UUID
    connection_id: uuid.UUID
    raw_body: bytes
    headers: dict[str, str]
    query_params: dict[str, str]


@runtime_checkable
class ConnectorAdapter(Protocol):
    key: str
    kind: ConnectorKind
    auth_mode: ConnectorAuthMode
    capabilities: ConnectorCapabilities

    def health_check(
        self,
        *,
        credentials: dict[str, Any],
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> HealthCheckResult: ...

    def disconnect(
        self,
        *,
        credentials: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None: ...


@runtime_checkable
class OAuthConnectorAdapter(Protocol):
    def build_authorization_request(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> OAuthAuthorizationRequest: ...

    def complete_authorization(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        state_payload: dict[str, Any] | None = None,
    ) -> OAuthCompletionResult: ...

    def refresh_credentials(
        self,
        *,
        credentials: dict[str, Any],
    ) -> OAuthCompletionResult: ...


@runtime_checkable
class CredentialConnectorAdapter(Protocol):
    def validate_credentials(
        self,
        *,
        credentials: dict[str, Any],
    ) -> HealthCheckResult: ...


@runtime_checkable
class KnowledgeSourceConnectorAdapter(Protocol):
    def sync(
        self,
        *,
        credentials: dict[str, Any],
        sync_state: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
        sync_run_id: uuid.UUID,
    ) -> SyncResult: ...


@runtime_checkable
class ChannelConnectorAdapter(Protocol):
    """Channel-specific operations arrive in 9F; marker protocol for kind checks."""

    pass


@runtime_checkable
class WebhookConnectorAdapter(Protocol):
    def verify_and_handle_webhook(
        self,
        *,
        request: WebhookRequestContext,
        credentials: dict[str, Any] | None,
    ) -> WebhookHandleResult: ...
