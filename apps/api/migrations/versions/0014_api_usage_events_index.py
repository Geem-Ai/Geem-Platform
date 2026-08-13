"""Phase 7C — composite index for Workspace API usage reads.

Supports ``usage_events`` filtered by workspace + API key + time
(summary aggregation and paginated history). Partial index excludes
internal Workspace Chat rows (``api_key_id IS NULL``).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_api_usage_events_index"
down_revision: Union[str, None] = "0013_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_usage_events_workspace_api_key_created",
        "usage_events",
        ["workspace_id", "api_key_id", "created_at"],
        postgresql_where=sa.text("api_key_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_usage_events_workspace_api_key_created",
        table_name="usage_events",
    )
