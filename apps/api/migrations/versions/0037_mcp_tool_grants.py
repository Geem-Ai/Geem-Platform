"""Definition- and principal-pinned MCP Expert grants (Phase 13C).

Revision ID: 0037_mcp_tool_grants
Revises: 0036_mcp_server_inventory
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_mcp_tool_grants"
down_revision: Union[str, None] = "0036_mcp_server_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Platform Experts have NULL workspace_id and therefore can never satisfy
    # the grant's exact Workspace+Expert composite FK.
    op.create_unique_constraint(
        "uq_experts_workspace_id",
        "experts",
        ["workspace_id", "id"],
    )

    op.create_table(
        "mcp_tool_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mcp_server_tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_definition_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_classification", sa.String(length=32), nullable=True),
        sa.Column(
            "approved_principal_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column("approved_credential_epoch", sa.Integer(), nullable=True),
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column(
            "allow_workspace_chat",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "allow_public_api",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "unattended_write_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outbound_data_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "unattended_write_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            name="fk_mcp_tool_grants_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "expert_id"],
            ["experts.workspace_id", "experts.id"],
            name="fk_mcp_tool_grants_workspace_expert",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_connection_id"],
            ["app_connections.workspace_id", "app_connections.id"],
            name="fk_mcp_tool_grants_workspace_connection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_connection_id", "mcp_server_tool_id"],
            [
                "mcp_server_tools.workspace_id",
                "mcp_server_tools.app_connection_id",
                "mcp_server_tools.id",
            ],
            name="fk_mcp_tool_grants_exact_tool",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_mcp_tool_grants_approved_by",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"],
            ["users.id"],
            name="fk_mcp_tool_grants_revoked_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "expert_id",
            "mcp_server_tool_id",
            name="uq_mcp_tool_grants_expert_tool",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_mcp_tool_grants_workspace_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "expert_id",
            "app_connection_id",
            "mcp_server_tool_id",
            "id",
            name="uq_mcp_tool_grants_exact_chain_id",
        ),
        sa.CheckConstraint(
            "state IN ('pending_review','active','revoked','stale_definition',"
            "'stale_classification','stale_principal')",
            name="ck_mcp_tool_grants_state",
        ),
        sa.CheckConstraint(
            "approved_classification IS NULL OR "
            "approved_classification IN ('read_only','write')",
            name="ck_mcp_tool_grants_approved_classification",
        ),
        sa.CheckConstraint(
            "approved_credential_epoch IS NULL OR approved_credential_epoch >= 1",
            name="ck_mcp_tool_grants_credential_epoch",
        ),
        sa.CheckConstraint(
            "state <> 'active' OR ("
            "approved_definition_hash IS NOT NULL AND "
            "approved_classification IS NOT NULL AND "
            "approved_principal_fingerprint IS NOT NULL AND "
            "approved_credential_epoch IS NOT NULL AND "
            "approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL AND "
            "outbound_data_acknowledged_at IS NOT NULL)",
            name="ck_mcp_tool_grants_active_review",
        ),
        sa.CheckConstraint(
            "NOT unattended_write_allowed OR ("
            "approved_classification = 'write' AND allow_public_api AND "
            "unattended_write_acknowledged_at IS NOT NULL)",
            name="ck_mcp_tool_grants_unattended_write",
        ),
    )
    op.create_index(
        "ix_mcp_tool_grants_workspace_id",
        "mcp_tool_grants",
        ["workspace_id"],
    )
    op.create_index(
        "ix_mcp_tool_grants_workspace_expert_state",
        "mcp_tool_grants",
        ["workspace_id", "expert_id", "state"],
    )
    op.create_index(
        "ix_mcp_tool_grants_workspace_connection",
        "mcp_tool_grants",
        ["workspace_id", "app_connection_id"],
    )


def downgrade() -> None:
    op.drop_table("mcp_tool_grants")
    op.drop_constraint(
        "uq_experts_workspace_id",
        "experts",
        type_="unique",
    )
