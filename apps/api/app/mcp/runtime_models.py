"""Phase 13D/13E MCP invocation, approval, surface, and delivery ledgers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class McpToolInvocation(Base):
    """Immutable admission identity plus monotonic remote execution state."""

    __tablename__ = "mcp_tool_invocations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "admission_id",
            name="uq_mcp_invocations_workspace_admission",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_mcp_invocations_workspace_idempotency",
        ),
        UniqueConstraint(
            "workspace_id",
            "request_id",
            "model_tool_call_id",
            name="uq_mcp_invocations_request_tool_call",
        ),
        UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_invocations_workspace_id"
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "expert_id",
                "app_connection_id",
                "mcp_server_tool_id",
                "mcp_tool_grant_id",
            ],
            [
                "mcp_tool_grants.workspace_id",
                "mcp_tool_grants.expert_id",
                "mcp_tool_grants.app_connection_id",
                "mcp_tool_grants.mcp_server_tool_id",
                "mcp_tool_grants.id",
            ],
            name="fk_mcp_invocations_exact_grant_chain",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "mcp_server_tool_id"],
            ["mcp_server_tools.workspace_id", "mcp_server_tools.id"],
            name="fk_mcp_invocations_workspace_tool",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "app_connection_id"],
            ["app_connections.workspace_id", "app_connections.id"],
            name="fk_mcp_invocations_workspace_connection",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_surface_binding_id"],
            [
                "mcp_tool_surface_bindings.workspace_id",
                "mcp_tool_surface_bindings.id",
            ],
            name="fk_mcp_invocations_workspace_surface",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_mcp_invocations_workspace_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_invocations_conversation_message",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "invocation_source IN ('workspace','api','widget','channel')",
            name="ck_mcp_invocations_source",
        ),
        CheckConstraint(
            "(invocation_source = 'workspace' AND initiated_by_user_id IS NOT NULL "
            "AND api_key_id IS NULL AND mcp_tool_surface_binding_id IS NULL "
            "AND conversation_id IS NOT NULL AND message_id IS NOT NULL) OR "
            "(invocation_source = 'api' AND initiated_by_user_id IS NULL "
            "AND api_key_id IS NOT NULL AND mcp_tool_surface_binding_id IS NULL "
            "AND conversation_id IS NULL AND message_id IS NULL) OR "
            "(invocation_source IN ('widget','channel') AND initiated_by_user_id IS NULL "
            "AND api_key_id IS NULL AND mcp_tool_surface_binding_id IS NOT NULL "
            "AND conversation_id IS NOT NULL AND message_id IS NOT NULL "
            "AND external_principal_fingerprint IS NOT NULL)",
            name="ck_mcp_invocations_attribution",
        ),
        CheckConstraint(
            "status IN ('admitted','dispatching','succeeded','failed','outcome_unknown')",
            name="ck_mcp_invocations_status",
        ),
        CheckConstraint(
            "char_length(argument_hash) = 64",
            name="ck_mcp_invocations_argument_hash",
        ),
        CheckConstraint(
            "external_principal_fingerprint IS NULL OR "
            "char_length(external_principal_fingerprint) = 64",
            name="ck_mcp_invocations_external_principal_digest",
        ),
        CheckConstraint(
            "response_bytes IS NULL OR response_bytes >= 0",
            name="ck_mcp_invocations_response_bytes",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_mcp_invocations_duration",
        ),
        Index(
            "ix_mcp_invocations_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_mcp_invocations_workspace_status",
            "workspace_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    mcp_tool_grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mcp_server_tool_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invocation_source: Mapped[str] = mapped_column(String(32), nullable=False)
    initiated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="RESTRICT")
    )
    mcp_tool_surface_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    external_principal_fingerprint: Mapped[str | None] = mapped_column(String(128))
    model_tool_call_id: Mapped[str] = mapped_column(String(256), nullable=False)
    request_id: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    admission_id: Mapped[str] = mapped_column(String(256), nullable=False)
    quota_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_charged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gateway_dispatch_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="admitted", server_default="admitted"
    )
    error_code: Mapped[str | None] = mapped_column(String(128))
    argument_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_bytes: Mapped[int | None] = mapped_column(BigInteger)
    response_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class McpPendingToolCall(Base):
    """Encrypted authoritative write arguments and recoverable resume state."""

    __tablename__ = "mcp_pending_tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_mcp_pending_workspace_idempotency",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_mcp_pending_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "id",
            "mcp_tool_surface_binding_id",
            name="uq_mcp_pending_workspace_surface_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_mcp_pending_workspace_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_pending_conversation_message",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_grant_id"],
            ["mcp_tool_grants.workspace_id", "mcp_tool_grants.id"],
            name="fk_mcp_pending_workspace_grant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_surface_binding_id"],
            [
                "mcp_tool_surface_bindings.workspace_id",
                "mcp_tool_surface_bindings.id",
            ],
            name="fk_mcp_pending_workspace_surface",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(initiated_by_user_id IS NOT NULL AND mcp_tool_surface_binding_id IS NULL "
            "AND external_principal_fingerprint IS NULL AND initiating_origin_digest IS NULL "
            "AND external_turn_handle_digest IS NULL) OR "
            "(initiated_by_user_id IS NULL AND mcp_tool_surface_binding_id IS NOT NULL "
            "AND external_principal_fingerprint IS NOT NULL)",
            name="ck_mcp_pending_initiator",
        ),
        CheckConstraint(
            "status IN ('pending','approved','denied','expired','executing',"
            "'executed','outcome_unknown')",
            name="ck_mcp_pending_status",
        ),
        CheckConstraint(
            "version >= 1 AND resume_attempts >= 0",
            name="ck_mcp_pending_counters",
        ),
        CheckConstraint(
            "expires_at <= purge_after",
            name="ck_mcp_pending_retention_window",
        ),
        CheckConstraint(
            "external_principal_fingerprint IS NULL OR "
            "char_length(external_principal_fingerprint) = 64",
            name="ck_mcp_pending_external_principal_digest",
        ),
        CheckConstraint(
            "initiating_origin_digest IS NULL OR "
            "char_length(initiating_origin_digest) = 64",
            name="ck_mcp_pending_origin_digest",
        ),
        CheckConstraint(
            "external_turn_handle_digest IS NULL OR "
            "char_length(external_turn_handle_digest) = 64",
            name="ck_mcp_pending_turn_digest",
        ),
        CheckConstraint(
            "(initiating_origin_digest IS NULL) = "
            "(external_turn_handle_digest IS NULL)",
            name="ck_mcp_pending_widget_digest_pair",
        ),
        CheckConstraint(
            "status IN ('denied','expired','executed','outcome_unknown') OR "
            "(arguments_encrypted IS NOT NULL AND loop_state_encrypted IS NOT NULL)",
            name="ck_mcp_pending_live_payload",
        ),
        CheckConstraint(
            "gateway_dispatch_started_at IS NULL OR "
            "status IN ('executing','executed','outcome_unknown')",
            name="ck_mcp_pending_dispatch_marker",
        ),
        CheckConstraint(
            "status <> 'executing' OR "
            "(claim_lease_expires_at IS NOT NULL AND execution_deadline IS NOT NULL)",
            name="ck_mcp_pending_executing_lease",
        ),
        Index(
            "uq_mcp_pending_external_live_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text(
                "mcp_tool_surface_binding_id IS NOT NULL AND "
                "status IN ('pending','approved','executing')"
            ),
        ),
        Index(
            "uq_mcp_pending_external_turn_receipt",
            "mcp_tool_surface_binding_id",
            "initiating_origin_digest",
            "external_turn_handle_digest",
            unique=True,
            postgresql_where=text("external_turn_handle_digest IS NOT NULL"),
        ),
        Index(
            "ix_mcp_pending_recovery",
            "status",
            "resume_requested_at",
            "claim_lease_expires_at",
        ),
        Index("ix_mcp_pending_purge", "purge_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mcp_tool_grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    initiated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    mcp_tool_surface_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    model_tool_call_id: Mapped[str] = mapped_column(String(256), nullable=False)
    external_principal_fingerprint: Mapped[str | None] = mapped_column(String(128))
    initiating_origin_digest: Mapped[str | None] = mapped_column(String(128))
    external_turn_handle_digest: Mapped[str | None] = mapped_column(String(128))
    arguments_encrypted: Mapped[str | None] = mapped_column(Text)
    loop_state_encrypted: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    resume_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    claim_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gateway_dispatch_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    execution_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class McpToolSurfaceBinding(Base):
    """Default-off exact Widget or WhatsApp exposure of one active grant."""

    __tablename__ = "mcp_tool_surface_bindings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_surface_bindings_workspace_id"
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            "widget_instance_id",
            name="uq_mcp_surface_bindings_workspace_widget_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "expert_id", "mcp_tool_grant_id"],
            [
                "mcp_tool_grants.workspace_id",
                "mcp_tool_grants.expert_id",
                "mcp_tool_grants.id",
            ],
            name="fk_mcp_surface_workspace_expert_grant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "expert_id", "widget_instance_id"],
            [
                "widget_instances.workspace_id",
                "widget_instances.expert_id",
                "widget_instances.id",
            ],
            name="fk_mcp_surface_exact_widget",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "expert_id", "channel_binding_id"],
            [
                "channel_bindings.workspace_id",
                "channel_bindings.expert_id",
                "channel_bindings.id",
            ],
            name="fk_mcp_surface_exact_channel",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(surface_kind = 'chat_widget' AND widget_instance_id IS NOT NULL "
            "AND channel_binding_id IS NULL) OR "
            "(surface_kind = 'whatsapp_openwa' AND widget_instance_id IS NULL "
            "AND channel_binding_id IS NOT NULL)",
            name="ck_mcp_surface_exact_target",
        ),
        CheckConstraint(
            "state IN ('active','revoked','stale_source','stale_classification')",
            name="ck_mcp_surface_state",
        ),
        CheckConstraint(
            "write_policy IN ('deny','workspace_operator_approval')",
            name="ck_mcp_surface_write_policy",
        ),
        CheckConstraint(
            "approved_source_epoch >= 1",
            name="ck_mcp_surface_source_epoch",
        ),
        CheckConstraint(
            "char_length(approved_surface_config_hash) = 64",
            name="ck_mcp_surface_config_hash",
        ),
        CheckConstraint(
            "char_length(approved_source_principal_fingerprint) = 64",
            name="ck_mcp_surface_principal_digest",
        ),
        Index(
            "uq_mcp_surface_active_widget_grant",
            "mcp_tool_grant_id",
            "widget_instance_id",
            unique=True,
            postgresql_where=text("state = 'active' AND widget_instance_id IS NOT NULL"),
        ),
        Index(
            "uq_mcp_surface_active_channel_grant",
            "mcp_tool_grant_id",
            "channel_binding_id",
            unique=True,
            postgresql_where=text("state = 'active' AND channel_binding_id IS NOT NULL"),
        ),
        Index(
            "ix_mcp_surface_workspace_expert",
            "workspace_id",
            "expert_id",
            "state",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    expert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    mcp_tool_grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    surface_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    widget_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    channel_binding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="revoked", server_default="revoked"
    )
    write_policy: Mapped[str] = mapped_column(
        String(48), nullable=False, default="deny", server_default="deny"
    )
    approved_surface_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_source_principal_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    approved_source_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    public_risk_acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    outbound_data_acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    approved_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class McpWidgetTurnReceipt(Base):
    """Idempotent, audience-bound logical Widget turn receipt."""

    __tablename__ = "mcp_widget_turn_receipts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_widget_receipts_workspace_id"
        ),
        UniqueConstraint(
            "widget_instance_id",
            "widget_conversation_binding_id",
            "client_turn_id_digest",
            name="uq_mcp_widget_receipts_client_turn",
        ),
        UniqueConstraint(
            "widget_instance_id",
            "initiating_origin_digest",
            "external_turn_handle_digest",
            name="uq_mcp_widget_receipts_turn_handle",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "widget_instance_id"],
            ["widget_instances.workspace_id", "widget_instances.id"],
            name="fk_mcp_widget_receipts_workspace_widget",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "widget_conversation_binding_id",
                "widget_instance_id",
                "conversation_id",
                "expert_id",
            ],
            [
                "widget_conversation_bindings.workspace_id",
                "widget_conversation_bindings.id",
                "widget_conversation_bindings.widget_instance_id",
                "widget_conversation_bindings.conversation_id",
                "widget_conversation_bindings.expert_id",
            ],
            name="fk_mcp_widget_receipts_exact_binding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "user_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_widget_receipts_user_message",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "assistant_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_widget_receipts_assistant_message",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('accepted','running','pending','completed','failed','outcome_unknown')",
            name="ck_mcp_widget_receipts_status",
        ),
        CheckConstraint(
            "char_length(request_content_hash) = 64 AND "
            "char_length(client_turn_id_digest) = 64 AND "
            "char_length(session_id_digest) = 64 AND "
            "char_length(initiating_origin_digest) = 64 AND "
            "char_length(external_turn_handle_digest) = 64",
            name="ck_mcp_widget_receipts_digests",
        ),
        Index(
            "ix_mcp_widget_receipts_status",
            "workspace_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    widget_instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    widget_conversation_binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_turn_id_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    initiating_origin_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    external_turn_handle_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="accepted", server_default="accepted"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class McpSurfaceDelivery(Base):
    """Immutable rendered external segment with CAS/lease delivery state."""

    __tablename__ = "mcp_surface_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_deliveries_workspace_id"
        ),
        UniqueConstraint(
            "assistant_message_id",
            "response_revision",
            "segment_index",
            name="uq_mcp_deliveries_message_revision_segment",
        ),
        UniqueConstraint(
            "widget_instance_id",
            "initiating_origin_digest",
            "external_turn_handle_digest",
            "response_revision",
            "segment_index",
            name="uq_mcp_deliveries_widget_turn_receipt",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_surface_binding_id"],
            [
                "mcp_tool_surface_bindings.workspace_id",
                "mcp_tool_surface_bindings.id",
            ],
            name="fk_mcp_deliveries_workspace_surface",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "workspace_id",
                "mcp_pending_tool_call_id",
                "mcp_tool_surface_binding_id",
            ],
            [
                "mcp_pending_tool_calls.workspace_id",
                "mcp_pending_tool_calls.id",
                "mcp_pending_tool_calls.mcp_tool_surface_binding_id",
            ],
            name="fk_mcp_deliveries_exact_pending_surface",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_mcp_deliveries_workspace_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "assistant_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_deliveries_conversation_message",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_surface_binding_id", "widget_instance_id"],
            [
                "mcp_tool_surface_bindings.workspace_id",
                "mcp_tool_surface_bindings.id",
                "mcp_tool_surface_bindings.widget_instance_id",
            ],
            name="fk_mcp_deliveries_exact_widget_surface",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending','dispatching','sent','delivery_unknown',"
            "'cancelled','expired')",
            name="ck_mcp_deliveries_status",
        ),
        CheckConstraint(
            "(widget_instance_id IS NULL AND initiating_origin_digest IS NULL "
            "AND external_turn_handle_digest IS NULL) OR "
            "(widget_instance_id IS NOT NULL AND initiating_origin_digest IS NOT NULL "
            "AND external_turn_handle_digest IS NOT NULL)",
            name="ck_mcp_deliveries_widget_receipt_shape",
        ),
        CheckConstraint(
            "reconciliation_resolution IS NULL OR "
            "reconciliation_resolution IN ('delivered','not_delivered')",
            name="ck_mcp_deliveries_reconciliation",
        ),
        CheckConstraint(
            "response_revision >= 1 AND conversation_sequence >= 1 "
            "AND segment_index >= 0 AND version >= 1 AND attempts >= 0",
            name="ck_mcp_deliveries_counters",
        ),
        CheckConstraint(
            "char_length(content_hash) = 64",
            name="ck_mcp_deliveries_content_hash",
        ),
        CheckConstraint(
            "initiating_origin_digest IS NULL OR "
            "char_length(initiating_origin_digest) = 64",
            name="ck_mcp_deliveries_origin_digest",
        ),
        CheckConstraint(
            "external_turn_handle_digest IS NULL OR "
            "char_length(external_turn_handle_digest) = 64",
            name="ck_mcp_deliveries_turn_digest",
        ),
        CheckConstraint(
            "status <> 'dispatching' OR "
            "(claim_lease_expires_at IS NOT NULL AND claimed_at IS NOT NULL)",
            name="ck_mcp_deliveries_dispatch_lease",
        ),
        CheckConstraint(
            "status = 'dispatching' OR claim_lease_expires_at IS NULL",
            name="ck_mcp_deliveries_terminal_lease",
        ),
        CheckConstraint(
            "(reconciliation_resolution IS NULL AND reconciled_by_user_id IS NULL "
            "AND reconciled_at IS NULL) OR "
            "(reconciliation_resolution = 'delivered' AND status = 'sent' "
            "AND reconciled_by_user_id IS NOT NULL AND reconciled_at IS NOT NULL) OR "
            "(reconciliation_resolution = 'not_delivered' AND status = 'cancelled' "
            "AND reconciled_by_user_id IS NOT NULL AND reconciled_at IS NOT NULL)",
            name="ck_mcp_deliveries_reconciliation_state",
        ),
        Index(
            "ix_mcp_deliveries_claim",
            "status",
            "claim_lease_expires_at",
            "delivery_deadline",
        ),
        Index(
            "ix_mcp_deliveries_conversation_order",
            "conversation_id",
            "conversation_sequence",
            "segment_index",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    mcp_pending_tool_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    mcp_tool_surface_binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    widget_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )
    initiating_origin_digest: Mapped[str | None] = mapped_column(String(128))
    external_turn_handle_digest: Mapped[str | None] = mapped_column(String(128))
    response_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    conversation_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    rendered_segment_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    claim_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(256))
    reconciled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciliation_resolution: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


__all__ = [
    "McpPendingToolCall",
    "McpSurfaceDelivery",
    "McpToolInvocation",
    "McpToolSurfaceBinding",
    "McpWidgetTurnReceipt",
]
