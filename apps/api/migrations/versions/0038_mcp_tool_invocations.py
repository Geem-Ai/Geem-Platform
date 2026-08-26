"""Durable idempotent MCP tool invocation ledger (Phase 13D).

Revision ID: 0038_mcp_tool_invocations
Revises: 0037_mcp_tool_grants
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_mcp_tool_invocations"
down_revision: Union[str, None] = "0037_mcp_tool_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_conversations_workspace_id",
        "conversations",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_messages_conversation_id",
        "messages",
        ["conversation_id", "id"],
    )

    op.create_table(
        "mcp_tool_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mcp_tool_grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_server_tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invocation_source", sa.String(length=32), nullable=False),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_tool_call_id", sa.String(length=256), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("admission_id", sa.String(length=256), nullable=False),
        sa.Column("quota_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quota_charged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gateway_dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="admitted",
        ),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("argument_hash", sa.String(length=64), nullable=False),
        sa.Column("response_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "response_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_mcp_invocations_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_connection_id"],
            ["app_connections.workspace_id", "app_connections.id"],
            name="fk_mcp_invocations_workspace_connection",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "mcp_server_tool_id"],
            ["mcp_server_tools.workspace_id", "mcp_server_tools.id"],
            name="fk_mcp_invocations_workspace_tool",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_mcp_invocations_workspace_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_invocations_conversation_message",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            ["users.id"],
            name="fk_mcp_invocations_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["api_keys.id"],
            name="fk_mcp_invocations_api_key",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_invocations_workspace_id"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "admission_id",
            name="uq_mcp_invocations_workspace_admission",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_mcp_invocations_workspace_idempotency",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "request_id",
            "model_tool_call_id",
            name="uq_mcp_invocations_request_tool_call",
        ),
        sa.CheckConstraint(
            "invocation_source IN ('workspace','api')",
            name="ck_mcp_invocations_source",
        ),
        sa.CheckConstraint(
            "(invocation_source = 'workspace' AND initiated_by_user_id IS NOT NULL "
            "AND api_key_id IS NULL AND conversation_id IS NOT NULL "
            "AND message_id IS NOT NULL) OR "
            "(invocation_source = 'api' AND initiated_by_user_id IS NULL "
            "AND api_key_id IS NOT NULL AND conversation_id IS NULL "
            "AND message_id IS NULL)",
            name="ck_mcp_invocations_attribution",
        ),
        sa.CheckConstraint(
            "status IN ('admitted','dispatching','succeeded','failed','outcome_unknown')",
            name="ck_mcp_invocations_status",
        ),
        sa.CheckConstraint(
            "char_length(argument_hash) = 64",
            name="ck_mcp_invocations_argument_hash",
        ),
        sa.CheckConstraint(
            "response_bytes IS NULL OR response_bytes >= 0",
            name="ck_mcp_invocations_response_bytes",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_mcp_invocations_duration",
        ),
    )
    op.create_index(
        "ix_mcp_invocations_workspace_created",
        "mcp_tool_invocations",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_mcp_invocations_workspace_status",
        "mcp_tool_invocations",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("mcp_tool_invocations")
    op.drop_constraint(
        "uq_messages_conversation_id", "messages", type_="unique"
    )
    op.drop_constraint(
        "uq_conversations_workspace_id", "conversations", type_="unique"
    )
