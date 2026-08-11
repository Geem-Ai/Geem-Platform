"""Phase 4D — Geem General Expert knowledge_mode.

* ``experts.knowledge_mode`` — ``rag`` (default) | ``general``
* At most one non-deleted platform general Expert
* Seeds/ensures Geem General via application bootstrap (see migrations README)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_geem_general_expert"
down_revision: Union[str, None] = "0006_conversations_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "experts",
        sa.Column(
            "knowledge_mode",
            sa.String(length=32),
            nullable=False,
            server_default="rag",
        ),
    )
    op.create_check_constraint(
        "ck_experts_knowledge_mode",
        "experts",
        "knowledge_mode IN ('rag', 'general')",
    )
    op.create_index(
        "uq_experts_platform_general",
        "experts",
        ["knowledge_mode"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'platform' AND knowledge_mode = 'general' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_experts_platform_general", table_name="experts")
    op.drop_constraint("ck_experts_knowledge_mode", "experts", type_="check")
    op.drop_column("experts", "knowledge_mode")
