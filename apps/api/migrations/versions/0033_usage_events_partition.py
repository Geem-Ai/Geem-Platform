"""Phase 11C — monthly RANGE partition of usage_events.

Revision ID: 0033_usage_events_partition
Revises: 0032_usage_daily_workspace

Converts the heap ``usage_events`` table to ``PARTITION BY RANGE (created_at)``
with monthly children named ``usage_events_YYYY_MM``. Secondary indexes are
created on the empty replacement parent (temporary names) **before**
``ACCESS EXCLUSIVE``; the lock covers copy + swap + drop only. After the heap
is dropped, indexes are renamed to the canonical ``ix_usage_events_*`` names.

PostgreSQL cannot ``ALTER TABLE … PARTITION BY`` on an existing heap, so this
revision builds a replacement parent, copies every row under
``ACCESS EXCLUSIVE`` (writes pause for the copy + swap), then drops the heap
only after a count check.

``messages.usage_event_id`` loses its FK to ``usage_events.id`` because a
partitioned unique constraint must include ``created_at``. The column remains
as a logical UUID pointer.

Existing rows older than the future 13-month retention window are **preserved**;
Celery retention drops expired partitions after this conversion.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings
from app.usage.partitions import (
    PARENT_TABLE,
    add_months,
    create_monthly_partition,
    ensure_write_window_on_connection,
    iter_months,
    month_start,
    parent_is_partitioned,
)

revision: str = "0033_usage_events_partition"
down_revision: str | None = "0032_usage_daily_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTED = "usage_events_parted"
_LEGACY = "usage_events_heap_legacy"

_INDEXES = (
    ("ix_usage_events_operation_type", "CREATE INDEX {name} ON {table} (operation_type)"),
    ("ix_usage_events_document_id", "CREATE INDEX {name} ON {table} (document_id)"),
    ("ix_usage_events_workspace_id", "CREATE INDEX {name} ON {table} (workspace_id)"),
    ("ix_usage_events_user_id", "CREATE INDEX {name} ON {table} (user_id)"),
    ("ix_usage_events_expert_id", "CREATE INDEX {name} ON {table} (expert_id)"),
    ("ix_usage_events_conversation_id", "CREATE INDEX {name} ON {table} (conversation_id)"),
    ("ix_usage_events_message_id", "CREATE INDEX {name} ON {table} (message_id)"),
    ("ix_usage_events_api_key_id", "CREATE INDEX {name} ON {table} (api_key_id)"),
    (
        "ix_usage_events_workspace_created",
        "CREATE INDEX {name} ON {table} (workspace_id, created_at DESC)",
    ),
    (
        "ix_usage_events_workspace_api_key_created",
        "CREATE INDEX {name} ON {table} (workspace_id, api_key_id, created_at) "
        "WHERE api_key_id IS NOT NULL",
    ),
)

_OUTBOUND_FKS = (
    ("fk_usage_events_workspace_id", "workspace_id", "workspaces", "id"),
    ("fk_usage_events_user_id", "user_id", "users", "id"),
    ("fk_usage_events_expert_id", "expert_id", "experts", "id"),
    ("fk_usage_events_conversation_id", "conversation_id", "conversations", "id"),
    ("fk_usage_events_message_id", "message_id", "messages", "id"),
    ("fk_usage_events_api_key_id", "api_key_id", "api_keys", "id"),
)


def _relkind(conn, name: str) -> str | None:
    return conn.execute(
        sa.text(
            """
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = :name
            """
        ),
        {"name": name},
    ).scalar()


def _drop_messages_usage_fk(conn) -> None:
    names = conn.execute(
        sa.text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = rel.relnamespace
            WHERE n.nspname = current_schema()
              AND rel.relname = 'messages'
              AND con.contype = 'f'
              AND pg_get_constraintdef(con.oid) ILIKE '%usage_events%'
            """
        )
    ).scalars()
    for name in names:
        conn.execute(sa.text(f'ALTER TABLE messages DROP CONSTRAINT IF EXISTS "{name}"'))


def _ensure_historical_partitions(conn, parent: str) -> None:
    bounds = conn.execute(
        sa.text(f'SELECT MIN(created_at), MAX(created_at) FROM "{PARENT_TABLE}"')
    ).one()
    now = datetime.now(UTC)
    current = month_start(now)
    months: list[date] = []
    if bounds[0] is not None:
        months.extend(iter_months(month_start(bounds[0]), month_start(bounds[1])))
    settings = get_settings()
    ahead = int(settings.usage_events_partitions_ahead_months)
    months.extend(add_months(current, offset) for offset in range(0, ahead + 1))
    seen: set[date] = set()
    for month in months:
        if month in seen:
            continue
        seen.add(month)
        create_monthly_partition(conn, month, parent=parent)


def _add_outbound_fks(conn, table: str) -> None:
    for name, column, target, target_col in _OUTBOUND_FKS:
        conn.execute(
            sa.text(
                f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"'
            )
        )
        conn.execute(
            sa.text(
                f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" '
                f'FOREIGN KEY ({column}) REFERENCES {target}({target_col}) '
                "ON DELETE SET NULL"
            )
        )


_INDEX_SUFFIX = "_parted11c"


def _create_canonical_indexes(conn, table: str, *, suffix: str = "") -> None:
    for name, ddl in _INDEXES:
        target = f"{name}{suffix}"
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {target}"))
        conn.execute(sa.text(ddl.format(name=target, table=table)))


def _rename_parted_indexes(conn) -> None:
    for name, _ddl in _INDEXES:
        tmp = f"{name}{_INDEX_SUFFIX}"
        conn.execute(sa.text(f"ALTER INDEX IF EXISTS {tmp} RENAME TO {name}"))


def upgrade() -> None:
    conn = op.get_bind()
    if parent_is_partitioned(conn):
        ensure_write_window_on_connection(conn, get_settings())
        return
    if _relkind(conn, PARENT_TABLE) is None:
        raise RuntimeError("usage_events does not exist; cannot partition")

    _drop_messages_usage_fk(conn)
    conn.execute(sa.text(f'DROP TABLE IF EXISTS "{_PARTED}" CASCADE'))
    conn.execute(
        sa.text(
            f'CREATE TABLE "{_PARTED}" '
            f'(LIKE "{PARENT_TABLE}" INCLUDING DEFAULTS INCLUDING STORAGE) '
            "PARTITION BY RANGE (created_at)"
        )
    )
    conn.execute(
        sa.text(f'ALTER TABLE "{_PARTED}" ALTER COLUMN created_at SET NOT NULL')
    )
    conn.execute(
        sa.text(
            f'ALTER TABLE "{_PARTED}" ADD PRIMARY KEY (id, created_at)'
        )
    )
    _ensure_historical_partitions(conn, _PARTED)
    # Build secondary indexes on the empty parent so INSERT maintains them.
    # Canonical names still belong to the heap until it is dropped.
    _create_canonical_indexes(conn, _PARTED, suffix=_INDEX_SUFFIX)

    conn.execute(sa.text(f'LOCK TABLE "{PARENT_TABLE}" IN ACCESS EXCLUSIVE MODE'))
    conn.execute(
        sa.text(
            f'INSERT INTO "{_PARTED}" SELECT * FROM "{PARENT_TABLE}"'
        )
    )
    old_count = conn.execute(sa.text(f'SELECT COUNT(*) FROM "{PARENT_TABLE}"')).scalar()
    new_count = conn.execute(sa.text(f'SELECT COUNT(*) FROM "{_PARTED}"')).scalar()
    if int(old_count or 0) != int(new_count or 0):
        raise RuntimeError(
            f"usage_events partition copy mismatch: heap={old_count} parted={new_count}"
        )

    conn.execute(sa.text(f'ALTER TABLE "{PARENT_TABLE}" RENAME TO "{_LEGACY}"'))
    conn.execute(sa.text(f'ALTER TABLE "{_PARTED}" RENAME TO "{PARENT_TABLE}"'))
    conn.execute(sa.text(f'DROP TABLE "{_LEGACY}"'))
    conn.execute(
        sa.text(
            f'ALTER TABLE "{PARENT_TABLE}" RENAME CONSTRAINT '
            f'"{_PARTED}_pkey" TO "{PARENT_TABLE}_pkey"'
        )
    )
    _rename_parted_indexes(conn)
    _add_outbound_fks(conn, PARENT_TABLE)
    ensure_write_window_on_connection(conn, get_settings())


def downgrade() -> None:
    """Rebuild a non-partitioned heap. Messages FK is restored."""
    conn = op.get_bind()
    if not parent_is_partitioned(conn):
        return
    heap = "usage_events_heap_restore"
    conn.execute(sa.text(f'DROP TABLE IF EXISTS "{heap}" CASCADE'))
    conn.execute(
        sa.text(
            f'CREATE TABLE "{heap}" '
            f'(LIKE "{PARENT_TABLE}" INCLUDING DEFAULTS INCLUDING STORAGE)'
        )
    )
    conn.execute(sa.text(f'INSERT INTO "{heap}" SELECT * FROM "{PARENT_TABLE}"'))
    old_count = conn.execute(sa.text(f'SELECT COUNT(*) FROM "{PARENT_TABLE}"')).scalar()
    new_count = conn.execute(sa.text(f'SELECT COUNT(*) FROM "{heap}"')).scalar()
    if int(old_count or 0) != int(new_count or 0):
        raise RuntimeError("usage_events downgrade copy mismatch")
    conn.execute(sa.text(f'ALTER TABLE "{heap}" ADD PRIMARY KEY (id)'))
    children = conn.execute(
        sa.text(
            """
            SELECT child.relname
            FROM pg_inherits i
            JOIN pg_class child ON child.oid = i.inhrelid
            JOIN pg_class parent ON parent.oid = i.inhparent
            WHERE parent.relname = :parent
            """
        ),
        {"parent": PARENT_TABLE},
    ).scalars()
    conn.execute(sa.text(f'DROP TABLE "{PARENT_TABLE}" CASCADE'))
    for _name in children:
        pass
    conn.execute(sa.text(f'ALTER TABLE "{heap}" RENAME TO "{PARENT_TABLE}"'))
    _create_canonical_indexes(conn, PARENT_TABLE)
    _add_outbound_fks(conn, PARENT_TABLE)
    conn.execute(
        sa.text(
            "ALTER TABLE messages ADD CONSTRAINT messages_usage_event_id_fkey "
            "FOREIGN KEY (usage_event_id) REFERENCES usage_events(id) ON DELETE SET NULL"
        )
    )
