"""Credential and sync-state encryption boundary (Phase 9C).

Adapters must not perform arbitrary DB crypto — use this service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.common.crypto import decrypt_json, encrypt_json
from app.connectors.models import AppConnection
from app.core.config import Settings, get_settings


class ConnectorCredentialService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def encrypt(self, payload: dict[str, Any]) -> str:
        return encrypt_json(payload, settings=self.settings)

    def decrypt(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        return decrypt_json(token, settings=self.settings)

    def get_credentials(self, connection: AppConnection) -> dict[str, Any] | None:
        return self.decrypt(connection.credentials_encrypted)

    def set_credentials(
        self,
        connection: AppConnection,
        credentials: dict[str, Any],
        *,
        expires_at: datetime | None = None,
    ) -> None:
        connection.credentials_encrypted = self.encrypt(credentials)
        if expires_at is not None:
            connection.credentials_expires_at = expires_at

    def replace_credentials(
        self,
        connection: AppConnection,
        credentials: dict[str, Any],
        *,
        expires_at: datetime | None = None,
    ) -> None:
        self.set_credentials(connection, credentials, expires_at=expires_at)

    def clear_credentials(self, connection: AppConnection) -> None:
        connection.credentials_encrypted = None
        connection.credentials_expires_at = None
        connection.webhook_routing_token_encrypted = None
        # Keep hash until reconnect regenerates — cleared so old URLs stop resolving.
        connection.webhook_routing_token_hash = None

    def get_sync_state(self, connection: AppConnection) -> dict[str, Any] | None:
        return self.decrypt(connection.sync_state_encrypted)

    def set_sync_state(
        self, connection: AppConnection, state: dict[str, Any] | None
    ) -> None:
        if state is None:
            connection.sync_state_encrypted = None
        else:
            connection.sync_state_encrypted = self.encrypt(state)

    def clear_sync_state(self, connection: AppConnection) -> None:
        connection.sync_state_encrypted = None

    def clear_all_secrets(self, connection: AppConnection) -> None:
        """Disconnect / revoke — destroy usable local secrets."""
        self.clear_credentials(connection)
        self.clear_sync_state(connection)
        connection.updated_at = datetime.now(timezone.utc)
