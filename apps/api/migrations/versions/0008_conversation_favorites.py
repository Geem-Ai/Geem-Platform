"""Phase 4 polish — conversation favorites (favorited_at).

Mirrors pinned_at: nullable timestamptz; is_favorite derived in the app layer.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_conversation_favorites"
down_revision: Union[str, None] = "0007_geem_general_expert"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("favorited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_conversations_workspace_user_favorited",
        "conversations",
        ["workspace_id", "user_id", "favorited_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversations_workspace_user_favorited",
        table_name="conversations",
    )
    op.drop_column("conversations", "favorited_at")
