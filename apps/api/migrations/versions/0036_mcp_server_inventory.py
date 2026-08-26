"""MCP connection state and normalized server tool inventory (Phase 13B).

Revision ID: 0036_mcp_server_inventory
Revises: 0035_audit_logs_created_at_index
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_mcp_server_inventory"
down_revision: Union[str, None] = "0035_audit_logs_created_at_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # These supporting unique keys let every tenant relationship include the
    # Workspace in its FK instead of trusting repository filters alone.
    op.create_unique_constraint(
        "uq_app_installations_workspace_id",
        "app_installations",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_app_connections_workspace_id",
        "app_connections",
        ["workspace_id", "id"],
    )
    op.create_foreign_key(
        "fk_app_connections_workspace_installation",
        "app_connections",
        "app_installations",
        ["workspace_id", "app_installation_id"],
        ["workspace_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "ck_app_connections_auth_mode",
        "app_connections",
        type_="check",
    )
    op.create_check_constraint(
        "ck_app_connections_auth_mode",
        "app_connections",
        "auth_mode IN ('none','oauth2','api_key','custom')",
    )

    op.add_column(
        "app_connections",
        sa.Column("mcp_protocol_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "app_connections",
        sa.Column("mcp_session_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "app_connections",
        sa.Column(
            "mcp_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "app_connections",
        sa.Column(
            "mcp_credential_epoch",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "app_connections",
        sa.Column("mcp_principal_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "app_connections",
        sa.Column(
            "mcp_discovery_generation",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "app_connections",
        sa.Column("mcp_inventory_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "app_connections",
        sa.Column(
            "mcp_reauthorization_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "ck_app_connections_mcp_credential_epoch",
        "app_connections",
        "mcp_credential_epoch >= 1",
    )
    op.create_check_constraint(
        "ck_app_connections_mcp_discovery_generation",
        "app_connections",
        "mcp_discovery_generation >= 0",
    )

    op.create_table(
        "mcp_server_tools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("llm_tool_name", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "input_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "output_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "annotations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "raw_definition",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("normalization_version", sa.String(length=64), nullable=False),
        sa.Column("protocol_version", sa.String(length=32), nullable=False),
        sa.Column("compatibility_status", sa.String(length=32), nullable=False),
        sa.Column("compatibility_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "classification",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("discovery_generation", sa.Integer(), nullable=False),
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
            name="fk_mcp_server_tools_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "app_connection_id"],
            ["app_connections.workspace_id", "app_connections.id"],
            name="fk_mcp_server_tools_workspace_connection",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "app_connection_id",
            "tool_name",
            name="uq_mcp_server_tools_connection_name",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "llm_tool_name",
            name="uq_mcp_server_tools_workspace_alias",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_mcp_server_tools_workspace_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "app_connection_id",
            "id",
            name="uq_mcp_server_tools_workspace_connection_id",
        ),
        sa.CheckConstraint(
            "compatibility_status IN "
            "('compatible','unsupported_schema','unsupported_capability','malformed')",
            name="ck_mcp_server_tools_compatibility",
        ),
        sa.CheckConstraint(
            "classification IN ('read_only','write','unknown')",
            name="ck_mcp_server_tools_classification",
        ),
        sa.CheckConstraint(
            "status IN ('active','stale','withdrawn')",
            name="ck_mcp_server_tools_status",
        ),
        sa.CheckConstraint(
            "char_length(definition_hash) = 64",
            name="ck_mcp_server_tools_definition_hash",
        ),
        sa.CheckConstraint(
            "discovery_generation >= 1",
            name="ck_mcp_server_tools_discovery_generation",
        ),
    )
    op.create_index(
        "ix_mcp_server_tools_workspace_id",
        "mcp_server_tools",
        ["workspace_id"],
    )
    op.create_index(
        "ix_mcp_server_tools_app_connection_id",
        "mcp_server_tools",
        ["app_connection_id"],
    )
    op.create_index(
        "ix_mcp_server_tools_workspace_connection_status",
        "mcp_server_tools",
        ["workspace_id", "app_connection_id", "status"],
    )
    op.create_index(
        "ix_mcp_server_tools_workspace_classification",
        "mcp_server_tools",
        ["workspace_id", "classification"],
    )


def downgrade() -> None:
    op.drop_table("mcp_server_tools")

    op.drop_constraint(
        "ck_app_connections_mcp_discovery_generation",
        "app_connections",
        type_="check",
    )
    op.drop_constraint(
        "ck_app_connections_mcp_credential_epoch",
        "app_connections",
        type_="check",
    )
    op.drop_column("app_connections", "mcp_reauthorization_required")
    op.drop_column("app_connections", "mcp_inventory_refreshed_at")
    op.drop_column("app_connections", "mcp_discovery_generation")
    op.drop_column("app_connections", "mcp_principal_fingerprint")
    op.drop_column("app_connections", "mcp_credential_epoch")
    op.drop_column("app_connections", "mcp_capabilities")
    op.drop_column("app_connections", "mcp_session_mode")
    op.drop_column("app_connections", "mcp_protocol_version")

    op.drop_constraint(
        "ck_app_connections_auth_mode",
        "app_connections",
        type_="check",
    )
    op.create_check_constraint(
        "ck_app_connections_auth_mode",
        "app_connections",
        "auth_mode IN ('oauth2','api_key','custom')",
    )
    op.drop_constraint(
        "fk_app_connections_workspace_installation",
        "app_connections",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_app_connections_workspace_id",
        "app_connections",
        type_="unique",
    )
    op.drop_constraint(
        "uq_app_installations_workspace_id",
        "app_installations",
        type_="unique",
    )
