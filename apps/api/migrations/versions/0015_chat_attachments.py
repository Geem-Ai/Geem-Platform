"""Chat composer attachments — ephemeral Workspace blobs (not RAG Documents)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_chat_attachments"
down_revision: Union[str, None] = "0014_api_usage_events_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=200), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_chat_attachments_workspace_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_chat_attachments_uploaded_by",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_chat_attachments_workspace_user",
        "chat_attachments",
        ["workspace_id", "uploaded_by"],
    )
    op.create_index(
        "ix_chat_attachments_workspace_created",
        "chat_attachments",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_workspace_created", table_name="chat_attachments")
    op.drop_index("ix_chat_attachments_workspace_user", table_name="chat_attachments")
    op.drop_table("chat_attachments")
