"""Allow Phase 5C storage audit reasons on storage_usage_events.

``StorageUsageReason`` gained ``reserve``, ``release``, and ``restore`` when
reservation holds were added, but ``ck_storage_usage_events_reason`` still only
allowed the Phase 5A set (upload/delete/recompute/adjust).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0020_storage_event_reasons"
down_revision: Union[str, None] = "0019_connector_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD = "reason IN ('upload', 'delete', 'recompute', 'adjust')"
_NEW = (
    "reason IN ("
    "'upload', 'delete', 'recompute', 'adjust', "
    "'reserve', 'release', 'restore'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_storage_usage_events_reason", "storage_usage_events", type_="check")
    op.create_check_constraint(
        "ck_storage_usage_events_reason",
        "storage_usage_events",
        _NEW,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM storage_usage_events "
        "WHERE reason IN ('reserve', 'release', 'restore')"
    )
    op.drop_constraint("ck_storage_usage_events_reason", "storage_usage_events", type_="check")
    op.create_check_constraint(
        "ck_storage_usage_events_reason",
        "storage_usage_events",
        _OLD,
    )
