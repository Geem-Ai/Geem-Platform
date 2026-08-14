"""Alembic: chat attachment TTL (expires_at) + purge index."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_chat_attachment_expires"
down_revision: Union[str, None] = "0015_chat_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_attachments",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing rows (if any): expire 12h after created_at.
    op.execute(
        sa.text(
            "UPDATE chat_attachments "
            "SET expires_at = created_at + interval '12 hours' "
            "WHERE expires_at IS NULL"
        )
    )
    op.alter_column("chat_attachments", "expires_at", nullable=False)
    op.create_index(
        "ix_chat_attachments_expires_at",
        "chat_attachments",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_expires_at", table_name="chat_attachments")
    op.drop_column("chat_attachments", "expires_at")
