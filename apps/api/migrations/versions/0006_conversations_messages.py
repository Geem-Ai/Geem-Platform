"""Phase 4A — Conversations + Messages persistence.

* ``conversations`` — consumer Workspace + user + Expert; soft-delete
* ``messages`` — role/content/citations/status; optional usage_event_id

Conversation.workspace_id is the consumer tenant Workspace (not necessarily the
Expert's owning Workspace for Platform Experts).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_conversations_messages"
down_revision: Union[str, None] = "0005_experts_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expert_id"], ["experts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_conversations_workspace_user_updated",
        "conversations",
        ["workspace_id", "user_id", "updated_at"],
    )
    op.create_index(
        "ix_conversations_workspace_user_pinned",
        "conversations",
        ["workspace_id", "user_id", "pinned_at"],
    )
    op.create_index(
        "ix_conversations_workspace_expert",
        "conversations",
        ["workspace_id", "expert_id"],
    )
    op.create_index(
        "ix_conversations_workspace_user_active",
        "conversations",
        ["workspace_id", "user_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_conversations_deleted_at", "conversations", ["deleted_at"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("usage_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["usage_event_id"], ["usage_events.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_messages_usage_event_id", "messages", ["usage_event_id"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
