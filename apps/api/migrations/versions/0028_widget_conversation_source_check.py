"""Allow conversations.source=widget with null user_id — Alembic revision.

Revision ID: 0028_widget_source_check
Revises: 0027_widget_conv_bindings

0027 already recreates ``ck_conversations_source_user`` for greenfield installs.
This revision repairs environments where 0027 was applied before that check
change was added to the migration file (constraint still channel/api only).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0028_widget_source_check"
down_revision: Union[str, None] = "0027_widget_conv_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WIDGET_ALLOWED = (
    "(source = 'workspace' AND user_id IS NOT NULL) OR "
    "(source = 'channel' AND user_id IS NULL) OR "
    "(source = 'api' AND user_id IS NULL) OR "
    "(source = 'widget' AND user_id IS NULL)"
)

_PRE_WIDGET = (
    "(source = 'workspace' AND user_id IS NOT NULL) OR "
    "(source = 'channel' AND user_id IS NULL) OR "
    "(source = 'api' AND user_id IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint("ck_conversations_source_user", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_source_user",
        "conversations",
        _WIDGET_ALLOWED,
    )


def downgrade() -> None:
    op.drop_constraint("ck_conversations_source_user", "conversations", type_="check")
    op.create_check_constraint(
        "ck_conversations_source_user",
        "conversations",
        _PRE_WIDGET,
    )
