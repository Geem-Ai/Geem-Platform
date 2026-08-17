"""Test-only fake connector adapter (Phase 9C).

Never registered in production catalog / bootstrap.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.connectors.adapters import (
    ConnectorCapabilities,
    HealthCheckResult,
    OAuthAuthorizationRequest,
    OAuthCompletionResult,
    SyncResult,
    WebhookHandleResult,
    WebhookRequestContext,
)
from app.connectors.types import (
    ConnectionHealth,
    ConnectorAuthMode,
    ConnectorKind,
)


@dataclass
class FakeKnowledgeConnector:
    """Fake knowledge-source connector for lifecycle / sync / webhook tests."""

    key: str = "fake_knowledge"
    kind: ConnectorKind = ConnectorKind.KNOWLEDGE_SOURCE
    auth_mode: ConnectorAuthMode = ConnectorAuthMode.OAUTH2
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            supports_oauth=True,
            supports_credentials=False,
            supports_sync=True,
            supports_webhooks=True,
            supports_health_check=True,
        )
    )
    health_result: ConnectionHealth = ConnectionHealth.HEALTHY
    fail_health: bool = False
    fail_sync: bool = False
    sync_items: list[dict[str, Any]] = field(default_factory=list)
    webhook_secret: str = "test-webhook-secret"
    last_sync_state: dict[str, Any] | None = None
    disconnect_calls: int = 0

    def health_check(
        self,
        *,
        credentials: dict[str, Any],
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> HealthCheckResult:
        _ = connection_id, workspace_id
        if self.fail_health or not credentials.get("access_token"):
            return HealthCheckResult(
                health=ConnectionHealth.FAILED,
                error_code="connector_credentials_invalid",
                error_message="Invalid credentials",
            )
        return HealthCheckResult(health=self.health_result)

    def disconnect(
        self,
        *,
        credentials: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        _ = credentials, connection_id, workspace_id
        self.disconnect_calls += 1

    def build_authorization_request(
        self,
        *,
        state: str,
        redirect_uri: str,
        code_challenge: str | None = None,
        code_challenge_method: str | None = None,
    ) -> OAuthAuthorizationRequest:
        return OAuthAuthorizationRequest(
            authorization_url=f"https://example.test/oauth?state={state}&redirect={redirect_uri}",
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

    def complete_authorization(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        state_payload: dict[str, Any] | None = None,
    ) -> OAuthCompletionResult:
        _ = redirect_uri, state_payload
        return OAuthCompletionResult(
            credentials={
                "access_token": f"access-{code}",
                "refresh_token": f"refresh-{code}",
                "code_verifier_echo": code_verifier,
            },
            external_account_id="fake-account-1",
            external_account_name="Fake Account",
            display_name="Fake Connection",
            credentials_expires_at=datetime.now(timezone.utc),
        )

    def refresh_credentials(
        self, *, credentials: dict[str, Any]
    ) -> OAuthCompletionResult:
        return OAuthCompletionResult(
            credentials={
                **credentials,
                "access_token": f"refreshed-{credentials.get('access_token')}",
            },
            external_account_id="fake-account-1",
            external_account_name="Fake Account",
        )

    def sync(
        self,
        *,
        credentials: dict[str, Any],
        sync_state: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
        sync_run_id: uuid.UUID,
    ) -> SyncResult:
        _ = credentials, connection_id, workspace_id, sync_run_id
        if self.fail_sync:
            raise RuntimeError("sync failed with access_token=SECRET_TOKEN")
        cursor = (sync_state or {}).get("cursor", 0)
        new_state = {"cursor": int(cursor) + 1}
        self.last_sync_state = new_state
        seen = len(self.sync_items) or 1
        return SyncResult(
            items_seen=seen,
            items_created=seen,
            items_updated=0,
            items_deleted=0,
            items_failed=0,
            sync_state=new_state,
        )

    def verify_and_handle_webhook(
        self,
        *,
        request: WebhookRequestContext,
        credentials: dict[str, Any] | None,
    ) -> WebhookHandleResult:
        _ = credentials
        sig = request.headers.get("x-fake-signature", "")
        expected = hashlib.sha256(
            self.webhook_secret.encode() + request.raw_body
        ).hexdigest()
        if sig != expected:
            return WebhookHandleResult(
                accepted=False,
                error_code="connector_webhook_unauthorized",
            )
        event_id = request.headers.get("x-fake-event-id")
        return WebhookHandleResult(
            accepted=True,
            provider_event_id=event_id,
            idempotency_key=event_id,
            enqueue=True,
            enqueue_payload={"kind": "fake_change"},
            http_status=200,
            response_body=b'{"ok":true}',
        )


@dataclass
class FakeChannelConnector:
    key: str = "fake_channel"
    kind: ConnectorKind = ConnectorKind.CHANNEL
    auth_mode: ConnectorAuthMode = ConnectorAuthMode.API_KEY
    capabilities: ConnectorCapabilities = field(
        default_factory=lambda: ConnectorCapabilities(
            supports_oauth=False,
            supports_credentials=True,
            supports_sync=False,
            supports_webhooks=True,
            supports_health_check=True,
        )
    )

    def health_check(
        self,
        *,
        credentials: dict[str, Any],
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> HealthCheckResult:
        _ = connection_id, workspace_id
        if not credentials.get("api_key"):
            return HealthCheckResult(
                health=ConnectionHealth.FAILED,
                error_code="connector_credentials_invalid",
            )
        return HealthCheckResult(health=ConnectionHealth.HEALTHY)

    def disconnect(
        self,
        *,
        credentials: dict[str, Any] | None,
        connection_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> None:
        _ = credentials, connection_id, workspace_id

    def validate_credentials(
        self, *, credentials: dict[str, Any]
    ) -> HealthCheckResult:
        return self.health_check(
            credentials=credentials,
            connection_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
        )
