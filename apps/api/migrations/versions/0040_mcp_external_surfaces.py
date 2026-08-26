"""Exact MCP Widget/WhatsApp bindings and durable external delivery (13E).

Revision ID: 0040_mcp_external_surfaces
Revises: 0039_mcp_pending_tool_calls
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_mcp_external_surfaces"
down_revision: Union[str, None] = "0039_mcp_pending_tool_calls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    _add_source_epochs_and_exact_keys()
    _create_surface_bindings()
    _extend_invocations_and_pending()
    _create_widget_turn_receipts()
    _create_surface_deliveries()
    _seed_external_approval_permission()


def _add_source_epochs_and_exact_keys() -> None:
    op.add_column(
        "widget_instances",
        sa.Column(
            "mcp_source_epoch", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "widget_instances",
        sa.Column(
            "mcp_source_principal_fingerprint", sa.String(length=128), nullable=True
        ),
    )
    op.create_check_constraint(
        "ck_widget_instances_mcp_source_epoch",
        "widget_instances",
        "mcp_source_epoch >= 1",
    )
    op.create_check_constraint(
        "ck_widget_instances_mcp_principal_digest",
        "widget_instances",
        "mcp_source_principal_fingerprint IS NULL OR "
        "char_length(mcp_source_principal_fingerprint) = 64",
    )
    op.create_unique_constraint(
        "uq_widget_instances_workspace_id",
        "widget_instances",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_widget_instances_workspace_expert_id",
        "widget_instances",
        ["workspace_id", "expert_id", "id"],
    )
    op.create_unique_constraint(
        "uq_widget_conv_exact_chain",
        "widget_conversation_bindings",
        ["workspace_id", "widget_instance_id", "conversation_id", "expert_id"],
    )
    op.create_unique_constraint(
        "uq_widget_conv_exact_receipt_chain",
        "widget_conversation_bindings",
        ["workspace_id", "id", "widget_instance_id", "conversation_id", "expert_id"],
    )

    op.add_column(
        "channel_bindings",
        sa.Column(
            "mcp_source_epoch", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "channel_bindings",
        sa.Column(
            "mcp_source_principal_fingerprint", sa.String(length=128), nullable=True
        ),
    )
    op.create_check_constraint(
        "ck_channel_bindings_mcp_source_epoch",
        "channel_bindings",
        "mcp_source_epoch >= 1",
    )
    op.create_check_constraint(
        "ck_channel_bindings_mcp_principal_digest",
        "channel_bindings",
        "mcp_source_principal_fingerprint IS NULL OR "
        "char_length(mcp_source_principal_fingerprint) = 64",
    )
    op.create_unique_constraint(
        "uq_channel_bindings_workspace_id",
        "channel_bindings",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_channel_bindings_workspace_expert_id",
        "channel_bindings",
        ["workspace_id", "expert_id", "id"],
    )
    op.create_unique_constraint(
        "uq_channel_bindings_exact_chain",
        "channel_bindings",
        ["workspace_id", "app_connection_id", "expert_id", "id"],
    )
    op.create_unique_constraint(
        "uq_channel_conv_exact_chain",
        "channel_conversation_bindings",
        ["workspace_id", "app_connection_id", "conversation_id", "expert_id"],
    )
    op.create_unique_constraint(
        "uq_mcp_tool_grants_workspace_expert_id",
        "mcp_tool_grants",
        ["workspace_id", "expert_id", "id"],
    )


def _create_surface_bindings() -> None:
    op.create_table(
        "mcp_tool_surface_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_tool_grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("surface_kind", sa.String(length=32), nullable=False),
        sa.Column("widget_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel_binding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "state", sa.String(length=32), nullable=False, server_default="revoked"
        ),
        sa.Column(
            "write_policy", sa.String(length=48), nullable=False, server_default="deny"
        ),
        sa.Column("approved_surface_config_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "approved_source_principal_fingerprint",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column("approved_source_epoch", sa.Integer(), nullable=False),
        sa.Column(
            "public_risk_acknowledged_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "outbound_data_acknowledged_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_mcp_surface_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "expert_id", "mcp_tool_grant_id"],
            [
                "mcp_tool_grants.workspace_id",
                "mcp_tool_grants.expert_id",
                "mcp_tool_grants.id",
            ],
            name="fk_mcp_surface_workspace_expert_grant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "expert_id", "widget_instance_id"],
            [
                "widget_instances.workspace_id",
                "widget_instances.expert_id",
                "widget_instances.id",
            ],
            name="fk_mcp_surface_exact_widget",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "expert_id", "channel_binding_id"],
            [
                "channel_bindings.workspace_id",
                "channel_bindings.expert_id",
                "channel_bindings.id",
            ],
            name="fk_mcp_surface_exact_channel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_mcp_surface_approved_by",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_surface_bindings_workspace_id"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            "widget_instance_id",
            name="uq_mcp_surface_bindings_workspace_widget_id",
        ),
        sa.CheckConstraint(
            "(surface_kind = 'chat_widget' AND widget_instance_id IS NOT NULL "
            "AND channel_binding_id IS NULL) OR "
            "(surface_kind = 'whatsapp_openwa' AND widget_instance_id IS NULL "
            "AND channel_binding_id IS NOT NULL)",
            name="ck_mcp_surface_exact_target",
        ),
        sa.CheckConstraint(
            "state IN ('active','revoked','stale_source','stale_classification')",
            name="ck_mcp_surface_state",
        ),
        sa.CheckConstraint(
            "write_policy IN ('deny','workspace_operator_approval')",
            name="ck_mcp_surface_write_policy",
        ),
        sa.CheckConstraint(
            "approved_source_epoch >= 1", name="ck_mcp_surface_source_epoch"
        ),
        sa.CheckConstraint(
            "char_length(approved_surface_config_hash) = 64",
            name="ck_mcp_surface_config_hash",
        ),
        sa.CheckConstraint(
            "char_length(approved_source_principal_fingerprint) = 64",
            name="ck_mcp_surface_principal_digest",
        ),
    )
    op.create_index(
        "uq_mcp_surface_active_widget_grant",
        "mcp_tool_surface_bindings",
        ["mcp_tool_grant_id", "widget_instance_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND widget_instance_id IS NOT NULL"),
    )
    op.create_index(
        "uq_mcp_surface_active_channel_grant",
        "mcp_tool_surface_bindings",
        ["mcp_tool_grant_id", "channel_binding_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND channel_binding_id IS NOT NULL"),
    )
    op.create_index(
        "ix_mcp_surface_workspace_expert",
        "mcp_tool_surface_bindings",
        ["workspace_id", "expert_id", "state"],
    )


def _extend_invocations_and_pending() -> None:
    op.add_column(
        "mcp_tool_invocations",
        sa.Column("mcp_tool_surface_binding_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mcp_tool_invocations",
        sa.Column("external_principal_fingerprint", sa.String(length=128), nullable=True),
    )
    op.create_foreign_key(
        "fk_mcp_invocations_workspace_surface",
        "mcp_tool_invocations",
        "mcp_tool_surface_bindings",
        ["workspace_id", "mcp_tool_surface_binding_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_mcp_invocations_source", "mcp_tool_invocations", type_="check"
    )
    op.drop_constraint(
        "ck_mcp_invocations_attribution", "mcp_tool_invocations", type_="check"
    )
    op.create_check_constraint(
        "ck_mcp_invocations_source",
        "mcp_tool_invocations",
        "invocation_source IN ('workspace','api','widget','channel')",
    )
    op.create_check_constraint(
        "ck_mcp_invocations_attribution",
        "mcp_tool_invocations",
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
    )
    op.create_check_constraint(
        "ck_mcp_invocations_external_principal_digest",
        "mcp_tool_invocations",
        "external_principal_fingerprint IS NULL OR "
        "char_length(external_principal_fingerprint) = 64",
    )

    op.add_column(
        "mcp_pending_tool_calls",
        sa.Column("mcp_tool_surface_binding_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "mcp_pending_tool_calls",
        sa.Column("external_principal_fingerprint", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "mcp_pending_tool_calls",
        sa.Column("initiating_origin_digest", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "mcp_pending_tool_calls",
        sa.Column("external_turn_handle_digest", sa.String(length=128), nullable=True),
    )
    op.alter_column(
        "mcp_pending_tool_calls",
        "initiated_by_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_mcp_pending_workspace_surface",
        "mcp_pending_tool_calls",
        "mcp_tool_surface_bindings",
        ["workspace_id", "mcp_tool_surface_binding_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_mcp_pending_workspace_surface_id",
        "mcp_pending_tool_calls",
        ["workspace_id", "id", "mcp_tool_surface_binding_id"],
    )
    op.create_check_constraint(
        "ck_mcp_pending_initiator",
        "mcp_pending_tool_calls",
        "(initiated_by_user_id IS NOT NULL AND mcp_tool_surface_binding_id IS NULL "
        "AND external_principal_fingerprint IS NULL AND initiating_origin_digest IS NULL "
        "AND external_turn_handle_digest IS NULL) OR "
        "(initiated_by_user_id IS NULL AND mcp_tool_surface_binding_id IS NOT NULL "
        "AND external_principal_fingerprint IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_mcp_pending_external_principal_digest",
        "mcp_pending_tool_calls",
        "external_principal_fingerprint IS NULL OR "
        "char_length(external_principal_fingerprint) = 64",
    )
    op.create_check_constraint(
        "ck_mcp_pending_origin_digest",
        "mcp_pending_tool_calls",
        "initiating_origin_digest IS NULL OR "
        "char_length(initiating_origin_digest) = 64",
    )
    op.create_check_constraint(
        "ck_mcp_pending_turn_digest",
        "mcp_pending_tool_calls",
        "external_turn_handle_digest IS NULL OR "
        "char_length(external_turn_handle_digest) = 64",
    )
    op.create_check_constraint(
        "ck_mcp_pending_widget_digest_pair",
        "mcp_pending_tool_calls",
        "(initiating_origin_digest IS NULL) = "
        "(external_turn_handle_digest IS NULL)",
    )
    op.create_index(
        "uq_mcp_pending_external_live_conversation",
        "mcp_pending_tool_calls",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text(
            "mcp_tool_surface_binding_id IS NOT NULL AND "
            "status IN ('pending','approved','executing')"
        ),
    )
    op.create_index(
        "uq_mcp_pending_external_turn_receipt",
        "mcp_pending_tool_calls",
        [
            "mcp_tool_surface_binding_id",
            "initiating_origin_digest",
            "external_turn_handle_digest",
        ],
        unique=True,
        postgresql_where=sa.text("external_turn_handle_digest IS NOT NULL"),
    )


def _create_widget_turn_receipts() -> None:
    op.create_table(
        "mcp_widget_turn_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("widget_instance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "widget_conversation_binding_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_content_hash", sa.String(length=64), nullable=False),
        sa.Column("client_turn_id_digest", sa.String(length=64), nullable=False),
        sa.Column("session_id_digest", sa.String(length=64), nullable=False),
        sa.Column("initiating_origin_digest", sa.String(length=64), nullable=False),
        sa.Column("external_turn_handle_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="accepted"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "widget_instance_id"],
            ["widget_instances.workspace_id", "widget_instances.id"],
            name="fk_mcp_widget_receipts_workspace_widget",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["conversation_id", "user_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_widget_receipts_user_message",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "assistant_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_widget_receipts_assistant_message",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_widget_receipts_workspace_id"
        ),
        sa.UniqueConstraint(
            "widget_instance_id",
            "widget_conversation_binding_id",
            "client_turn_id_digest",
            name="uq_mcp_widget_receipts_client_turn",
        ),
        sa.UniqueConstraint(
            "widget_instance_id",
            "initiating_origin_digest",
            "external_turn_handle_digest",
            name="uq_mcp_widget_receipts_turn_handle",
        ),
        sa.CheckConstraint(
            "status IN ('accepted','running','pending','completed','failed','outcome_unknown')",
            name="ck_mcp_widget_receipts_status",
        ),
        sa.CheckConstraint(
            "char_length(request_content_hash) = 64 AND "
            "char_length(client_turn_id_digest) = 64 AND "
            "char_length(session_id_digest) = 64 AND "
            "char_length(initiating_origin_digest) = 64 AND "
            "char_length(external_turn_handle_digest) = 64",
            name="ck_mcp_widget_receipts_digests",
        ),
    )
    op.create_index(
        "ix_mcp_widget_receipts_status",
        "mcp_widget_turn_receipts",
        ["workspace_id", "status", "updated_at"],
    )


def _create_surface_deliveries() -> None:
    op.create_table(
        "mcp_surface_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_pending_tool_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assistant_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_tool_surface_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("widget_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("initiating_origin_digest", sa.String(length=128), nullable=True),
        sa.Column("external_turn_handle_digest", sa.String(length=128), nullable=True),
        sa.Column("response_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("conversation_sequence", sa.BigInteger(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("rendered_segment_encrypted", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("claim_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_message_id", sa.String(length=256), nullable=True),
        sa.Column("reconciled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciliation_resolution", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_mcp_deliveries_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_surface_binding_id"],
            ["mcp_tool_surface_bindings.workspace_id", "mcp_tool_surface_bindings.id"],
            name="fk_mcp_deliveries_workspace_surface",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "mcp_pending_tool_call_id", "mcp_tool_surface_binding_id"],
            [
                "mcp_pending_tool_calls.workspace_id",
                "mcp_pending_tool_calls.id",
                "mcp_pending_tool_calls.mcp_tool_surface_binding_id",
            ],
            name="fk_mcp_deliveries_exact_pending_surface",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_mcp_deliveries_workspace_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "assistant_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_deliveries_conversation_message",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_surface_binding_id", "widget_instance_id"],
            [
                "mcp_tool_surface_bindings.workspace_id",
                "mcp_tool_surface_bindings.id",
                "mcp_tool_surface_bindings.widget_instance_id",
            ],
            name="fk_mcp_deliveries_exact_widget_surface",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reconciled_by_user_id"],
            ["users.id"],
            name="fk_mcp_deliveries_reconciled_by",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_deliveries_workspace_id"
        ),
        sa.UniqueConstraint(
            "assistant_message_id",
            "response_revision",
            "segment_index",
            name="uq_mcp_deliveries_message_revision_segment",
        ),
        sa.UniqueConstraint(
            "widget_instance_id",
            "initiating_origin_digest",
            "external_turn_handle_digest",
            "response_revision",
            "segment_index",
            name="uq_mcp_deliveries_widget_turn_receipt",
        ),
        sa.CheckConstraint(
            "status IN ('pending','dispatching','sent','delivery_unknown',"
            "'cancelled','expired')",
            name="ck_mcp_deliveries_status",
        ),
        sa.CheckConstraint(
            "(widget_instance_id IS NULL AND initiating_origin_digest IS NULL "
            "AND external_turn_handle_digest IS NULL) OR "
            "(widget_instance_id IS NOT NULL AND initiating_origin_digest IS NOT NULL "
            "AND external_turn_handle_digest IS NOT NULL)",
            name="ck_mcp_deliveries_widget_receipt_shape",
        ),
        sa.CheckConstraint(
            "reconciliation_resolution IS NULL OR "
            "reconciliation_resolution IN ('delivered','not_delivered')",
            name="ck_mcp_deliveries_reconciliation",
        ),
        sa.CheckConstraint(
            "response_revision >= 1 AND conversation_sequence >= 1 "
            "AND segment_index >= 0 AND version >= 1 AND attempts >= 0",
            name="ck_mcp_deliveries_counters",
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64",
            name="ck_mcp_deliveries_content_hash",
        ),
        sa.CheckConstraint(
            "initiating_origin_digest IS NULL OR "
            "char_length(initiating_origin_digest) = 64",
            name="ck_mcp_deliveries_origin_digest",
        ),
        sa.CheckConstraint(
            "external_turn_handle_digest IS NULL OR "
            "char_length(external_turn_handle_digest) = 64",
            name="ck_mcp_deliveries_turn_digest",
        ),
        sa.CheckConstraint(
            "status <> 'dispatching' OR "
            "(claim_lease_expires_at IS NOT NULL AND claimed_at IS NOT NULL)",
            name="ck_mcp_deliveries_dispatch_lease",
        ),
        sa.CheckConstraint(
            "status = 'dispatching' OR claim_lease_expires_at IS NULL",
            name="ck_mcp_deliveries_terminal_lease",
        ),
        sa.CheckConstraint(
            "(reconciliation_resolution IS NULL AND reconciled_by_user_id IS NULL "
            "AND reconciled_at IS NULL) OR "
            "(reconciliation_resolution = 'delivered' AND status = 'sent' "
            "AND reconciled_by_user_id IS NOT NULL AND reconciled_at IS NOT NULL) OR "
            "(reconciliation_resolution = 'not_delivered' AND status = 'cancelled' "
            "AND reconciled_by_user_id IS NOT NULL AND reconciled_at IS NOT NULL)",
            name="ck_mcp_deliveries_reconciliation_state",
        ),
    )
    op.create_index(
        "ix_mcp_deliveries_claim",
        "mcp_surface_deliveries",
        ["status", "claim_lease_expires_at", "delivery_deadline"],
    )
    op.create_index(
        "ix_mcp_deliveries_conversation_order",
        "mcp_surface_deliveries",
        ["conversation_id", "conversation_sequence", "segment_index"],
    )


def _seed_external_approval_permission() -> None:
    permission_id = str(uuid.uuid4())
    op.execute(
        sa.text(
            """
            INSERT INTO permissions
                (id, key, name_key, description_key, group_key, owner_only,
                 created_at, updated_at)
            SELECT CAST(:permission_id AS uuid), 'mcp_tools.approve_external',
                   'permissions.mcp_tools.approve_external.name',
                   'permissions.mcp_tools.approve_external.description',
                   'mcp_tools', false, now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM permissions WHERE key = 'mcp_tools.approve_external'
            )
            """
        ).bindparams(permission_id=permission_id)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO workspace_role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM workspace_roles AS r
            JOIN permissions AS p ON p.key = 'mcp_tools.approve_external'
            WHERE r.system_key IN ('owner', 'admin')
            ON CONFLICT DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM workspace_role_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions WHERE key = 'mcp_tools.approve_external'
            )
            """
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE key = 'mcp_tools.approve_external'")
    )

    op.drop_table("mcp_surface_deliveries")
    op.drop_table("mcp_widget_turn_receipts")
    # 0039 cannot represent external-surface attribution. Downgrade therefore
    # removes Phase 13E-only operational rows explicitly before restoring its
    # NOT NULL/source constraints; Workspace/API records remain intact.
    op.execute(
        sa.text(
            """
            DELETE FROM mcp_pending_tool_calls
            WHERE mcp_tool_surface_binding_id IS NOT NULL
               OR initiated_by_user_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM mcp_tool_invocations
            WHERE invocation_source IN ('widget', 'channel')
               OR mcp_tool_surface_binding_id IS NOT NULL
            """
        )
    )
    op.drop_index(
        "uq_mcp_pending_external_turn_receipt",
        table_name="mcp_pending_tool_calls",
    )
    op.drop_index(
        "uq_mcp_pending_external_live_conversation",
        table_name="mcp_pending_tool_calls",
    )
    op.drop_constraint(
        "ck_mcp_pending_widget_digest_pair",
        "mcp_pending_tool_calls",
        type_="check",
    )
    op.drop_constraint(
        "ck_mcp_pending_turn_digest", "mcp_pending_tool_calls", type_="check"
    )
    op.drop_constraint(
        "ck_mcp_pending_origin_digest", "mcp_pending_tool_calls", type_="check"
    )
    op.drop_constraint(
        "ck_mcp_pending_external_principal_digest",
        "mcp_pending_tool_calls",
        type_="check",
    )
    op.drop_constraint(
        "ck_mcp_pending_initiator", "mcp_pending_tool_calls", type_="check"
    )
    op.drop_constraint(
        "uq_mcp_pending_workspace_surface_id",
        "mcp_pending_tool_calls",
        type_="unique",
    )
    op.drop_constraint(
        "fk_mcp_pending_workspace_surface",
        "mcp_pending_tool_calls",
        type_="foreignkey",
    )
    op.alter_column(
        "mcp_pending_tool_calls",
        "initiated_by_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("mcp_pending_tool_calls", "external_turn_handle_digest")
    op.drop_column("mcp_pending_tool_calls", "initiating_origin_digest")
    op.drop_column("mcp_pending_tool_calls", "external_principal_fingerprint")
    op.drop_column("mcp_pending_tool_calls", "mcp_tool_surface_binding_id")

    op.drop_constraint(
        "ck_mcp_invocations_attribution", "mcp_tool_invocations", type_="check"
    )
    op.drop_constraint(
        "ck_mcp_invocations_external_principal_digest",
        "mcp_tool_invocations",
        type_="check",
    )
    op.drop_constraint(
        "ck_mcp_invocations_source", "mcp_tool_invocations", type_="check"
    )
    op.create_check_constraint(
        "ck_mcp_invocations_source",
        "mcp_tool_invocations",
        "invocation_source IN ('workspace','api')",
    )
    op.create_check_constraint(
        "ck_mcp_invocations_attribution",
        "mcp_tool_invocations",
        "(invocation_source = 'workspace' AND initiated_by_user_id IS NOT NULL "
        "AND api_key_id IS NULL AND conversation_id IS NOT NULL "
        "AND message_id IS NOT NULL) OR "
        "(invocation_source = 'api' AND initiated_by_user_id IS NULL "
        "AND api_key_id IS NOT NULL AND conversation_id IS NULL "
        "AND message_id IS NULL)",
    )
    op.drop_constraint(
        "fk_mcp_invocations_workspace_surface",
        "mcp_tool_invocations",
        type_="foreignkey",
    )
    op.drop_column("mcp_tool_invocations", "external_principal_fingerprint")
    op.drop_column("mcp_tool_invocations", "mcp_tool_surface_binding_id")

    op.drop_table("mcp_tool_surface_bindings")
    op.drop_constraint(
        "uq_mcp_tool_grants_workspace_expert_id",
        "mcp_tool_grants",
        type_="unique",
    )
    op.drop_constraint(
        "uq_channel_conv_exact_chain",
        "channel_conversation_bindings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_channel_bindings_exact_chain", "channel_bindings", type_="unique"
    )
    op.drop_constraint(
        "uq_channel_bindings_workspace_expert_id",
        "channel_bindings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_channel_bindings_workspace_id", "channel_bindings", type_="unique"
    )
    op.drop_constraint(
        "ck_channel_bindings_mcp_source_epoch", "channel_bindings", type_="check"
    )
    op.drop_constraint(
        "ck_channel_bindings_mcp_principal_digest",
        "channel_bindings",
        type_="check",
    )
    op.drop_column("channel_bindings", "mcp_source_principal_fingerprint")
    op.drop_column("channel_bindings", "mcp_source_epoch")
    op.drop_constraint(
        "uq_widget_conv_exact_receipt_chain",
        "widget_conversation_bindings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_widget_conv_exact_chain",
        "widget_conversation_bindings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_widget_instances_workspace_expert_id",
        "widget_instances",
        type_="unique",
    )
    op.drop_constraint(
        "uq_widget_instances_workspace_id", "widget_instances", type_="unique"
    )
    op.drop_constraint(
        "ck_widget_instances_mcp_source_epoch", "widget_instances", type_="check"
    )
    op.drop_constraint(
        "ck_widget_instances_mcp_principal_digest",
        "widget_instances",
        type_="check",
    )
    op.drop_column("widget_instances", "mcp_source_principal_fingerprint")
    op.drop_column("widget_instances", "mcp_source_epoch")
