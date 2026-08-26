"""Encrypted, actor-bound MCP write approvals (Phase 13E core).

Revision ID: 0039_mcp_pending_tool_calls
Revises: 0038_mcp_tool_invocations
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039_mcp_pending_tool_calls"
down_revision: Union[str, None] = "0038_mcp_tool_invocations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_pending_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_tool_grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_tool_call_id", sa.String(length=256), nullable=False),
        sa.Column("arguments_encrypted", sa.Text(), nullable=True),
        sa.Column("loop_state_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resume_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gateway_dispatch_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_mcp_pending_workspace_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_mcp_pending_conversation_message",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "mcp_tool_grant_id"],
            ["mcp_tool_grants.workspace_id", "mcp_tool_grants.id"],
            name="fk_mcp_pending_workspace_grant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            ["users.id"],
            name="fk_mcp_pending_initiated_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name="fk_mcp_pending_decided_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_mcp_pending_workspace_id"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_mcp_pending_workspace_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied','expired','executing',"
            "'executed','outcome_unknown')",
            name="ck_mcp_pending_status",
        ),
        sa.CheckConstraint(
            "version >= 1 AND resume_attempts >= 0",
            name="ck_mcp_pending_counters",
        ),
        sa.CheckConstraint(
            "expires_at <= purge_after",
            name="ck_mcp_pending_retention_window",
        ),
        sa.CheckConstraint(
            "status IN ('denied','expired','executed','outcome_unknown') OR "
            "(arguments_encrypted IS NOT NULL AND loop_state_encrypted IS NOT NULL)",
            name="ck_mcp_pending_live_payload",
        ),
        sa.CheckConstraint(
            "gateway_dispatch_started_at IS NULL OR "
            "status IN ('executing','executed','outcome_unknown')",
            name="ck_mcp_pending_dispatch_marker",
        ),
        sa.CheckConstraint(
            "status <> 'executing' OR "
            "(claim_lease_expires_at IS NOT NULL AND execution_deadline IS NOT NULL)",
            name="ck_mcp_pending_executing_lease",
        ),
    )
    op.create_index(
        "ix_mcp_pending_recovery",
        "mcp_pending_tool_calls",
        ["status", "resume_requested_at", "claim_lease_expires_at"],
    )
    op.create_index(
        "ix_mcp_pending_purge",
        "mcp_pending_tool_calls",
        ["purge_after"],
    )


def downgrade() -> None:
    op.drop_table("mcp_pending_tool_calls")
