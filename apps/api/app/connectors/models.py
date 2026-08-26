"""Connector persistence models (Phase 9C).

AppConnection is distinct from AppInstallation and commercial access.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.connectors.types import (
    ConnectionHealth,
    ConnectionStatus,
    ConnectorAuthMode,
    ConnectorItemStatus,
    ConnectorItemType,
    SyncRunStatus,
    SyncTrigger,
    WebhookEventStatus,
)
from app.db.session import Base
from app.workspaces.models import Workspace


class AppConnection(Base):
    """Workspace-owned external account/system connection."""

    __tablename__ = "app_connections"
    __table_args__ = (
        CheckConstraint(
            "mcp_credential_epoch >= 1",
            name="ck_app_connections_mcp_credential_epoch",
        ),
        CheckConstraint(
            "mcp_discovery_generation >= 0",
            name="ck_app_connections_mcp_discovery_generation",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_app_connections_workspace_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_installation_id"],
            ["app_installations.workspace_id", "app_installations.id"],
            name="fk_app_connections_workspace_installation",
            ondelete="RESTRICT",
        ),
        Index("ix_app_connections_workspace_installation", "workspace_id", "app_installation_id"),
        Index("ix_app_connections_workspace_connector", "workspace_id", "connector_key"),
        Index("ix_app_connections_workspace_status", "workspace_id", "status"),
        Index(
            "ix_app_connections_routing_token_hash",
            "webhook_routing_token_hash",
            unique=True,
            postgresql_where=text("webhook_routing_token_hash IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_installation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_installations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    connector_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_account_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    auth_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectorAuthMode.OAUTH2.value
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectionStatus.PENDING.value
    )
    health: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectionHealth.UNKNOWN.value
    )
    # Encrypted JSON — never expose via API.
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_state_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hash of high-entropy webhook routing token (not connection UUID).
    webhook_routing_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Encrypted plaintext routing token when providers need the URL material.
    webhook_routing_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Phase 13B — safe, queryable MCP protocol/identity state. Canonical
    # endpoint/resource URLs and all usable credentials remain inside the
    # encrypted credential blob above.
    mcp_protocol_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    mcp_session_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mcp_capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    mcp_credential_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    mcp_principal_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    mcp_discovery_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    mcp_inventory_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mcp_reauthorization_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship()
    sync_runs: Mapped[list[ConnectorSyncRun]] = relationship(back_populates="connection")
    items: Mapped[list[ConnectorItem]] = relationship(back_populates="connection")
    webhook_events: Mapped[list[ConnectorWebhookEvent]] = relationship(
        back_populates="connection"
    )


class ConnectorSyncRun(Base):
    """Knowledge-source sync execution record."""

    __tablename__ = "connector_sync_runs"
    __table_args__ = (
        Index(
            "ix_connector_sync_runs_workspace_connection_created",
            "workspace_id",
            "app_connection_id",
            "created_at",
        ),
        Index(
            "uq_connector_sync_runs_connection_idempotency",
            "app_connection_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    trigger: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SyncTrigger.MANUAL.value
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SyncRunStatus.PENDING.value
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    items_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    items_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    items_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    connection: Mapped[AppConnection] = relationship(back_populates="sync_runs")


class ConnectorItem(Base):
    """External resource known to an App connection (Drive file/folder, etc.)."""

    __tablename__ = "connector_items"
    __table_args__ = (
        UniqueConstraint(
            "app_connection_id",
            "external_id",
            name="uq_connector_items_connection_external",
        ),
        Index("ix_connector_items_workspace_connection", "workspace_id", "app_connection_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    parent_external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    item_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectorItemType.OTHER.value
    )
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_version: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectorItemStatus.ACTIVE.value
    )
    current_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at_provider: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    connection: Mapped[AppConnection] = relationship(back_populates="items")


class ConnectorWebhookEvent(Base):
    """Lightweight webhook idempotency / operational tracking (no raw body)."""

    __tablename__ = "connector_webhook_events"
    __table_args__ = (
        Index(
            "ix_connector_webhook_events_connection_provider_event",
            "app_connection_id",
            "provider_event_id",
        ),
        Index(
            "uq_connector_webhook_events_connection_provider_event",
            "app_connection_id",
            "provider_event_id",
            unique=True,
            postgresql_where=text("provider_event_id IS NOT NULL"),
        ),
        Index(
            "uq_connector_webhook_events_connection_idempotency",
            "app_connection_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_connections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WebhookEventStatus.RECEIVED.value
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    connection: Mapped[AppConnection] = relationship(back_populates="webhook_events")


class ChannelBinding(Base):
    """Expert + reply policy for a channel connection (Phase 9F)."""

    __tablename__ = "channel_bindings"
    __table_args__ = (
        CheckConstraint(
            "mcp_source_epoch >= 1", name="ck_channel_bindings_mcp_source_epoch"
        ),
        CheckConstraint(
            "mcp_source_principal_fingerprint IS NULL OR "
            "char_length(mcp_source_principal_fingerprint) = 64",
            name="ck_channel_bindings_mcp_principal_digest",
        ),
        UniqueConstraint(
            "workspace_id", "id", name="uq_channel_bindings_workspace_id"
        ),
        UniqueConstraint(
            "workspace_id",
            "expert_id",
            "id",
            name="uq_channel_bindings_workspace_expert_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "app_connection_id",
            "expert_id",
            "id",
            name="uq_channel_bindings_exact_chain",
        ),
        UniqueConstraint("app_connection_id", name="uq_channel_bindings_connection"),
        Index(
            "ix_channel_bindings_workspace_connection",
            "workspace_id",
            "app_connection_id",
        ),
        Index("ix_channel_bindings_workspace_expert", "workspace_id", "expert_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    expert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    auto_reply_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    respond_to_groups: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Exact MCP source identity/config epoch; ordinary WhatsApp remains unchanged.
    mcp_source_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    mcp_source_principal_fingerprint: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChannelConversationBinding(Base):
    """Maps an external channel chat to a Geem conversation."""

    __tablename__ = "channel_conversation_bindings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "app_connection_id",
            "conversation_id",
            "expert_id",
            name="uq_channel_conv_exact_chain",
        ),
        UniqueConstraint(
            "app_connection_id",
            "external_chat_id",
            "expert_id",
            name="uq_channel_conv_connection_chat_expert",
        ),
        UniqueConstraint("conversation_id", name="uq_channel_conv_conversation"),
        Index(
            "ix_channel_conv_workspace_connection",
            "workspace_id",
            "app_connection_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app_connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_chat_id: Mapped[str] = mapped_column(String(512), nullable=False)
    external_sender_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
