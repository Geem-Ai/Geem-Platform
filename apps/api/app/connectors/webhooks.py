"""Generic inbound webhook routing (Phase 9C).

Routing token ≠ connection UUID. Provider verification is mandatory.
Heavy work is enqueued — never performed inline.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.apps_catalog.access import AppAccessService
from app.apps_catalog.models import AppInstallationStatus
from app.apps_catalog.repository import AppCatalogRepository
from app.common.security_log import security_log
from app.connectors.adapters import WebhookRequestContext
from app.connectors.credentials import ConnectorCredentialService
from app.connectors.models import AppConnection, ConnectorWebhookEvent
from app.connectors.registry import ConnectorRegistry, connector_registry
from app.connectors.repository import ConnectorRepository, hash_routing_token
from app.connectors.sanitize import sanitize_error_message
from app.connectors.types import CONNECTION_USABLE_STATUSES, WebhookEventStatus
from app.core.errors import AppError, ErrorCategory

logger = logging.getLogger(__name__)

_OPENWA_CONNECTOR_KEY = "openwa"


class ConnectorWebhookDispatcher:
    def __init__(
        self,
        db: Session,
        *,
        registry: ConnectorRegistry | None = None,
        enqueue_fn: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or connector_registry
        self.repo = ConnectorRepository(db)
        self.catalog = AppCatalogRepository(db)
        self.access = AppAccessService(db)
        self.credentials = ConnectorCredentialService(db)
        self.enqueue_fn = enqueue_fn

    def dispatch(
        self,
        *,
        connector_key: str,
        routing_token: str,
        raw_body: bytes,
        headers: dict[str, str],
        query_params: dict[str, str],
    ) -> tuple[int, bytes, dict[str, str]]:
        if not routing_token or len(routing_token) < 16:
            logger.info(
                "connector_webhook_rejected",
                extra={"reason": "token_short", "connector_key": connector_key},
            )
            raise AppError(
                ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED,
                "Invalid webhook routing token.",
            )

        token_hash = hash_routing_token(routing_token)
        connection = self.repo.get_by_routing_token_hash(token_hash)
        if connection is None or connection.connector_key != connector_key:
            logger.info(
                "connector_webhook_rejected",
                extra={"reason": "token_unknown", "connector_key": connector_key},
            )
            raise AppError(
                ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED,
                "Invalid webhook routing token.",
            )

        installation = self.catalog.get_installation_by_id(connection.app_installation_id)
        if (
            installation is None
            or installation.workspace_id != connection.workspace_id
            or installation.status != AppInstallationStatus.ACTIVE.value
        ):
            self._maybe_revoke_openwa_webhooks(
                connection,
                raw_body=raw_body,
                headers=headers,
                reason="installation_inactive",
            )
            raise AppError(
                ErrorCategory.CONNECTOR_INSTALLATION_REQUIRED,
                "App installation is not active.",
            )
        app = self.catalog.get_app_by_id(installation.app_id)
        if app is None:
            self._maybe_revoke_openwa_webhooks(
                connection,
                raw_body=raw_body,
                headers=headers,
                reason="app_missing",
            )
            raise AppError(ErrorCategory.APP_NOT_FOUND, "App not found.")

        try:
            self.access.require_active(connection.workspace_id, app_slug=app.slug)
        except AppError:
            logger.info(
                "connector_webhook_rejected",
                extra={
                    "reason": "access",
                    "workspace_id": str(connection.workspace_id),
                    "connection_id": str(connection.id),
                },
            )
            self._maybe_revoke_openwa_webhooks(
                connection,
                raw_body=raw_body,
                headers=headers,
                reason="access_denied",
            )
            raise

        if connection.status not in CONNECTION_USABLE_STATUSES:
            self._maybe_revoke_openwa_webhooks(
                connection,
                raw_body=raw_body,
                headers=headers,
                reason="connection_unusable",
            )
            raise AppError(
                ErrorCategory.CONNECTOR_WEBHOOK_INVALID,
                "Connection is not usable for webhooks.",
                details={"status": connection.status},
            )

        if not self.registry.is_available(connector_key):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_AVAILABLE,
                "Connector adapter is not available.",
                details={"connector_key": connector_key},
            )
        adapter = self.registry.get(connector_key)
        if not hasattr(adapter, "verify_and_handle_webhook"):
            raise AppError(
                ErrorCategory.CONNECTOR_NOT_SUPPORTED,
                "Connector does not support webhooks.",
            )

        creds = self.credentials.get_credentials(connection)
        request = WebhookRequestContext(
            connector_key=connector_key,
            workspace_id=connection.workspace_id,
            connection_id=connection.id,
            raw_body=raw_body,
            headers=headers,
            query_params=query_params,
        )

        try:
            result = adapter.verify_and_handle_webhook(  # type: ignore[attr-defined]
                request=request,
                credentials=creds,
            )
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "connector_webhook_rejected",
                extra={
                    "reason": "verify_failed",
                    "connection_id": str(connection.id),
                    "error": sanitize_error_message(str(exc)),
                },
            )
            raise AppError(
                ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED,
                "Webhook verification failed.",
            ) from exc

        if not result.accepted:
            logger.info(
                "connector_webhook_rejected",
                extra={
                    "reason": result.error_code or "not_accepted",
                    "connection_id": str(connection.id),
                },
            )
            raise AppError(
                ErrorCategory.CONNECTOR_WEBHOOK_UNAUTHORIZED,
                "Webhook rejected by provider verifier.",
                details={"error_code": result.error_code},
            )

        # Microsoft Graph validationToken handshake — return plain text immediately.
        content_type = (result.response_headers or {}).get("Content-Type", "")
        if (
            result.ignore
            and result.response_body is not None
            and content_type.startswith("text/plain")
        ):
            return (
                result.http_status,
                result.response_body,
                dict(result.response_headers),
            )

        payload_hash = hashlib.sha256(raw_body).hexdigest() if raw_body else None

        # Idempotency: provider event id or derived key
        if result.provider_event_id:
            existing = self.repo.get_webhook_by_provider_event(
                connection.id, result.provider_event_id
            )
            if existing is not None:
                return (
                    result.http_status,
                    result.response_body or b"",
                    dict(result.response_headers),
                )
        if result.idempotency_key:
            existing = self.repo.get_webhook_by_idempotency(
                connection.id, result.idempotency_key
            )
            if existing is not None:
                return (
                    result.http_status,
                    result.response_body or b"",
                    dict(result.response_headers),
                )

        status = WebhookEventStatus.RECEIVED.value
        if result.ignore:
            status = WebhookEventStatus.IGNORED.value
        elif result.enqueue:
            status = WebhookEventStatus.QUEUED.value

        event = ConnectorWebhookEvent(
            workspace_id=connection.workspace_id,
            app_connection_id=connection.id,
            provider_event_id=result.provider_event_id,
            idempotency_key=result.idempotency_key,
            payload_hash=payload_hash,
            status=status,
            received_at=datetime.now(timezone.utc),
            processed_at=(
                datetime.now(timezone.utc)
                if status == WebhookEventStatus.IGNORED.value
                else None
            ),
        )
        try:
            self.repo.add_webhook_event(event)
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            # Duplicate — treat as idempotent success
            return (
                result.http_status,
                result.response_body or b"",
                dict(result.response_headers),
            )

        logger.info(
            "connector_webhook_received",
            extra={
                "workspace_id": str(connection.workspace_id),
                "connection_id": str(connection.id),
                "connector_key": connector_key,
                "event_id": str(event.id),
                "status": status,
                # Never log raw_body
            },
        )
        security_log(
            "connector_webhook_received",
            workspace_id=str(connection.workspace_id),
            connection_id=str(connection.id),
            connector_key=connector_key,
            event_id=str(event.id),
        )

        if result.enqueue and not result.ignore:
            # Tenant envelope is immutable — adapter payload is nested only.
            payload = {
                "workspace_id": str(connection.workspace_id),
                "connection_id": str(connection.id),
                "webhook_event_id": str(event.id),
                "connector_key": connector_key,
                "adapter_payload": dict(result.enqueue_payload or {}),
            }
            if self.enqueue_fn is not None:
                self.enqueue_fn(payload)
            else:
                from app.connectors.tasks import enqueue_connector_webhook_work

                enqueue_connector_webhook_work(payload)

        return (
            result.http_status,
            result.response_body or b"{}",
            dict(result.response_headers),
        )

    def _maybe_revoke_openwa_webhooks(
        self,
        connection: AppConnection,
        *,
        raw_body: bytes,
        headers: dict[str, str],
        reason: str,
    ) -> None:
        """On expired/inactive OpenWA deliveries, best-effort delete provider webhooks.

        Requires a valid HMAC when a webhook secret is present so a token-only
        caller cannot force teardown.
        """
        if connection.connector_key != _OPENWA_CONNECTOR_KEY:
            return
        creds = self.credentials.get_credentials(connection) or {}
        secret = str(creds.get("webhook_secret") or "").strip()
        if secret:
            from app.connectors.providers.openwa.webhook import (
                HEADER_SIGNATURE,
                verify_openwa_signature,
            )

            signature = headers.get(HEADER_SIGNATURE)
            if not verify_openwa_signature(
                raw_body=raw_body,
                signature=signature,
                secret=secret,
            ):
                return
        try:
            from app.connectors.providers.openwa.service import OpenWAChannelService

            OpenWAChannelService(self.db, registry=self.registry).ensure_webhook_removed(
                connection
            )
            self.db.flush()
            logger.info(
                "openwa_webhook_revoked_on_reject",
                extra={
                    "reason": reason,
                    "workspace_id": str(connection.workspace_id),
                    "connection_id": str(connection.id),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "openwa_webhook_revoke_failed",
                extra={
                    "reason": reason,
                    "connection_id": str(connection.id),
                    "error": sanitize_error_message(str(exc)),
                },
            )
