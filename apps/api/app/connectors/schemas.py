"""Public connector DTOs — never include credentials or sync state secrets."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.connectors.models import AppConnection, ConnectorSyncRun
from app.connectors.sanitize import sanitize_error_message
from app.connectors.types import (
    CONNECTION_USABLE_STATUSES,
    ConnectionHealth,
    ConnectionStatus,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ConnectorCapabilityOut(BaseModel):
    key: str
    kind: str | None = None
    available: bool = False
    auth_mode: str | None = None
    can_connect: bool = False
    supports_sync: bool = False
    supports_webhooks: bool = False
    supports_health_check: bool = False
    unavailable_reason: str | None = None


class ConnectionCapabilitiesOut(BaseModel):
    can_disconnect: bool = False
    can_delete: bool = False
    can_health_check: bool = False
    can_sync: bool = False
    can_reconnect: bool = False


class AppConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    app_installation_id: uuid.UUID
    app_slug: str
    connector_key: str
    connector_kind: str | None = None
    display_name: str | None = None
    external_account_id: str | None = None
    external_account_name: str | None = None
    auth_mode: str
    status: str
    health: str
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_health_check_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_error_at: datetime | None = None
    credentials_expires_at: datetime | None = None
    created_at: datetime | None = None
    authorization_url: str | None = None
    capabilities: ConnectionCapabilitiesOut = Field(
        default_factory=ConnectionCapabilitiesOut
    )


class StartConnectionRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    connection_id: uuid.UUID | None = None  # reconnect existing
    return_path: str | None = Field(default=None, max_length=512)
    connect_mode: Literal["qr", "pairing"] | None = "qr"


class OpenWAQrOut(BaseModel):
    status: str
    qr_code: str


class OpenWAPairingCodeRequest(BaseModel):
    phone_number: str = Field(min_length=6, max_length=32)


class OpenWAPairingCodeOut(BaseModel):
    status: str
    pairing_code: str


class ChannelSettingsUpdateRequest(BaseModel):
    expert_id: uuid.UUID | None = None
    auto_reply_enabled: bool | None = None
    respond_to_groups: bool | None = None
    enabled: bool | None = None


class WhatsAppConnectionOut(AppConnectionOut):
    channel_binding_id: uuid.UUID
    provider_status: str | None = None
    connect_mode: str | None = None
    phone: str | None = None
    expert_id: uuid.UUID | None = None
    enabled: bool = True
    auto_reply_enabled: bool = True
    respond_to_groups: bool = False


class AppConnectionListOut(BaseModel):
    # The shared list route returns richer channel DTOs for WhatsApp. Keep the
    # subtype in the response contract so FastAPI does not serialize it back to
    # AppConnectionOut and discard the exact ChannelBinding identifier.
    items: list[WhatsAppConnectionOut | AppConnectionOut]
    total: int
    limit: int
    offset: int
    used: int | None = None
    connection_limit: int | None = None


class GoogleDrivePickerSessionOut(BaseModel):
    access_token: str
    expires_at: datetime | None = None
    app_id: str | None = None
    developer_key: str | None = None


class MicrosoftOneDrivePickerSessionOut(BaseModel):
    access_token: str
    expires_at: datetime | None = None
    base_url: str
    client_id: str | None = None
    tenant: str | None = None
    drive_id: str | None = None
    account_kind: str = "work_school"
    picker_mode: str | None = None


class MicrosoftOneDrivePickerTokenRequest(BaseModel):
    resource: str = Field(min_length=8, max_length=512)


class MicrosoftOneDrivePickerTokenOut(BaseModel):
    access_token: str
    expires_at: datetime | None = None
    resource: str


class ConnectorSyncRunOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    app_connection_id: uuid.UUID
    trigger: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    items_seen: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_failed: int = 0
    error_code: str | None = None
    error_message: str | None = None
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime | None = None


class ConnectorSyncRunListOut(BaseModel):
    items: list[ConnectorSyncRunOut]
    total: int
    limit: int
    offset: int


class ManualSyncRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=256)


def to_connection_out(
    row: AppConnection,
    *,
    app_slug: str,
    connector_kind: str | None,
    can_manage: bool,
    adapter_available: bool,
    supports_sync: bool,
    authorization_url: str | None = None,
) -> AppConnectionOut:
    usable = row.status in CONNECTION_USABLE_STATUSES
    disconnected = row.status in {
        ConnectionStatus.DISCONNECTED.value,
        ConnectionStatus.REVOKED.value,
    }
    reconnectable = disconnected or row.status == ConnectionStatus.ERROR.value
    caps = ConnectionCapabilitiesOut(
        can_disconnect=bool(can_manage and not disconnected),
        can_delete=bool(can_manage and disconnected),
        can_health_check=bool(can_manage and usable and adapter_available),
        can_sync=bool(can_manage and usable and adapter_available and supports_sync),
        can_reconnect=bool(can_manage and reconnectable and adapter_available),
    )
    return AppConnectionOut(
        id=row.id,
        workspace_id=row.workspace_id,
        app_installation_id=row.app_installation_id,
        app_slug=app_slug,
        connector_key=row.connector_key,
        connector_kind=connector_kind,
        display_name=row.display_name,
        external_account_id=row.external_account_id,
        external_account_name=row.external_account_name,
        auth_mode=row.auth_mode,
        status=row.status,
        health=row.health or ConnectionHealth.UNKNOWN.value,
        connected_at=_utc(row.connected_at),
        disconnected_at=_utc(row.disconnected_at),
        last_health_check_at=_utc(row.last_health_check_at),
        last_success_at=_utc(row.last_success_at),
        last_error_code=row.last_error_code,
        last_error_message=sanitize_error_message(row.last_error_message),
        last_error_at=_utc(row.last_error_at),
        credentials_expires_at=_utc(row.credentials_expires_at),
        created_at=_utc(row.created_at),
        authorization_url=authorization_url,
        capabilities=caps,
    )


def to_sync_run_out(row: ConnectorSyncRun) -> ConnectorSyncRunOut:
    return ConnectorSyncRunOut(
        id=row.id,
        workspace_id=row.workspace_id,
        app_connection_id=row.app_connection_id,
        trigger=row.trigger,
        status=row.status,
        started_at=_utc(row.started_at),
        completed_at=_utc(row.completed_at),
        items_seen=int(row.items_seen or 0),
        items_created=int(row.items_created or 0),
        items_updated=int(row.items_updated or 0),
        items_deleted=int(row.items_deleted or 0),
        items_failed=int(row.items_failed or 0),
        error_code=row.error_code,
        error_message=sanitize_error_message(row.error_message),
        created_by_user_id=row.created_by_user_id,
        created_at=_utc(row.created_at),
    )


def assert_no_secrets(payload: dict[str, Any]) -> None:
    """Test/guard helper — raise if secret fields leak into a dict."""
    banned = {
        "credentials_encrypted",
        "config_encrypted",
        "sync_state_encrypted",
        "webhook_routing_token_encrypted",
        "webhook_routing_token_hash",
        "credentials",
        "access_token",
        "refresh_token",
        "code_verifier",
        "api_key",
        "client_secret",
        "webhook_secret",
        "session_id",
        "x_api_key",
        "X-API-Key",
    }
    found = banned.intersection(payload.keys())
    if found:
        raise AssertionError(f"Secret fields leaked: {sorted(found)}")
    for value in payload.values():
        if isinstance(value, dict):
            assert_no_secrets(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    assert_no_secrets(item)
