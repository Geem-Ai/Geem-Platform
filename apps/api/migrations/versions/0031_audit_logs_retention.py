"""Audit logs + workspace purged_at for retention tombstones (Phase 11A).

Revision ID: 0031_audit_logs_retention
Revises: 0030_email_verification
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_audit_logs_retention"
down_revision: Union[str, None] = "0030_email_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workspaces_purged_at", "workspaces", ["purged_at"])
    op.create_index(
        "ix_workspaces_purge_due",
        "workspaces",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL AND purged_at IS NULL"),
    )
    op.create_index(
        "ix_experts_purge_due",
        "experts",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.create_index(
        "ix_conversations_purge_due",
        "conversations",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_api_key_id"], ["api_keys.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_audit_logs_workspace_created", "audit_logs", ["workspace_id", "created_at"]
    )
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_actor_api_key_id", "audit_logs", ["actor_api_key_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_actor_api_key_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_workspace_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_workspace_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_conversations_purge_due", table_name="conversations")
    op.drop_index("ix_experts_purge_due", table_name="experts")
    op.drop_index("ix_workspaces_purge_due", table_name="workspaces")
    op.drop_index("ix_workspaces_purged_at", table_name="workspaces")
    op.drop_column("workspaces", "purged_at")
