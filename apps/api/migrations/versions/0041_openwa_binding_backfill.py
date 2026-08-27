"""Persist bindings for OpenWA connections created before Phase 9F.

Revision ID: 0041_openwa_binding_backfill
Revises: 0040_mcp_external_surfaces
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

revision: str = "0041_openwa_binding_backfill"
down_revision: Union[str, None] = "0040_mcp_external_surfaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_app_connections = sa.table(
    "app_connections",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
    sa.column("connector_key", sa.String(length=64)),
)
_channel_bindings = sa.table(
    "channel_bindings",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
    sa.column("app_connection_id", postgresql.UUID(as_uuid=True)),
    sa.column("expert_id", postgresql.UUID(as_uuid=True)),
    sa.column("enabled", sa.Boolean()),
    sa.column("auto_reply_enabled", sa.Boolean()),
    sa.column("respond_to_groups", sa.Boolean()),
)


def _backfill_openwa_channel_bindings(connection: Connection) -> int:
    """Create one durable default binding for each legacy OpenWA connection."""

    missing = connection.execute(
        sa.select(_app_connections.c.id, _app_connections.c.workspace_id)
        .where(
            _app_connections.c.connector_key == "openwa",
            ~sa.exists(
                sa.select(1).where(
                    _channel_bindings.c.app_connection_id
                    == _app_connections.c.id
                )
            ),
        )
        .order_by(_app_connections.c.id)
        .with_for_update(of=_app_connections)
    ).mappings().all()
    if not missing:
        return 0

    rows = [
        {
            "id": uuid.uuid4(),
            "workspace_id": row["workspace_id"],
            "app_connection_id": row["id"],
            "expert_id": None,
            "enabled": True,
            "auto_reply_enabled": True,
            "respond_to_groups": False,
        }
        for row in missing
    ]
    connection.execute(
        postgresql.insert(_channel_bindings)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["app_connection_id"])
    )
    # Psycopg may report -1 for a multi-row INSERT, so return the number of
    # locked candidates rather than exposing a driver-specific rowcount.
    return len(missing)


def upgrade() -> None:
    _backfill_openwa_channel_bindings(op.get_bind())


def downgrade() -> None:
    # This is a data repair, not a feature table.  A backfilled binding may have
    # been configured or referenced after upgrade, so deleting it is unsafe.
    pass
