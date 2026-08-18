"""Widget visitor session → conversation bindings — Alembic revision.

Revision ID: 0027_widget_conv_bindings
Revises: 0026_chat_widget
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_widget_conv_bindings"
down_revision: Union[str, None] = "0026_chat_widget"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow source=widget with null user_id (visitor threads).
    op.drop_constraint("ck_conversations_source_user", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_source_user",
        "conversations",
        "(source = 'workspace' AND user_id IS NOT NULL) OR "
        "(source = 'channel' AND user_id IS NULL) OR "
        "(source = 'api' AND user_id IS NULL) OR "
        "(source = 'widget' AND user_id IS NULL)",
    )

    op.create_table(
        "widget_conversation_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "widget_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("widget_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=128), nullable=False),
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
            "widget_instance_id",
            "session_id",
            "expert_id",
            name="uq_widget_conv_widget_session_expert",
        ),
        sa.UniqueConstraint("conversation_id", name="uq_widget_conv_conversation"),
    )
    op.create_index(
        "ix_widget_conversation_bindings_workspace_id",
        "widget_conversation_bindings",
        ["workspace_id"],
    )
    op.create_index(
        "ix_widget_conv_workspace_widget",
        "widget_conversation_bindings",
        ["workspace_id", "widget_instance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_widget_conv_workspace_widget",
        table_name="widget_conversation_bindings",
    )
    op.drop_index(
        "ix_widget_conversation_bindings_workspace_id",
        table_name="widget_conversation_bindings",
    )
    op.drop_table("widget_conversation_bindings")

    op.drop_constraint("ck_conversations_source_user", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_source_user",
        "conversations",
        "(source = 'workspace' AND user_id IS NOT NULL) OR "
        "(source = 'channel' AND user_id IS NULL) OR "
        "(source = 'api' AND user_id IS NULL)",
    )
