"""Phase 9F — OpenWA channel bindings + channel conversations.

Revision ID: 0022_openwa_channel
Revises: 0021_message_attachments
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_openwa_channel"
down_revision: Union[str, None] = "0021_message_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "app_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "expert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "auto_reply_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "respond_to_groups",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.UniqueConstraint(
            "app_connection_id",
            name="uq_channel_bindings_connection",
        ),
    )
    op.create_index(
        "ix_channel_bindings_workspace_connection",
        "channel_bindings",
        ["workspace_id", "app_connection_id"],
    )
    op.create_index(
        "ix_channel_bindings_workspace_expert",
        "channel_bindings",
        ["workspace_id", "expert_id"],
    )

    op.add_column(
        "conversations",
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="workspace",
        ),
    )
    op.alter_column(
        "conversations",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_conversations_source_user",
        "conversations",
        "(source = 'workspace' AND user_id IS NOT NULL) OR "
        "(source = 'channel' AND user_id IS NULL) OR "
        "(source = 'api' AND user_id IS NULL)",
    )
    op.create_index(
        "ix_conversations_workspace_source",
        "conversations",
        ["workspace_id", "source"],
    )

    op.create_table(
        "channel_conversation_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "app_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_chat_id", sa.String(length=512), nullable=False),
        sa.Column("external_sender_id", sa.String(length=512), nullable=True),
        sa.Column(
            "expert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
        sa.UniqueConstraint(
            "app_connection_id",
            "external_chat_id",
            "expert_id",
            name="uq_channel_conv_connection_chat_expert",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            name="uq_channel_conv_conversation",
        ),
    )
    op.create_index(
        "ix_channel_conv_workspace_connection",
        "channel_conversation_bindings",
        ["workspace_id", "app_connection_id"],
    )


def downgrade() -> None:
    op.drop_table("channel_conversation_bindings")
    op.drop_index("ix_conversations_workspace_source", table_name="conversations")
    op.drop_constraint("ck_conversations_source_user", "conversations", type_="check")
    op.alter_column(
        "conversations",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("conversations", "source")
    op.drop_table("channel_bindings")
