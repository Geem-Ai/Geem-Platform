"""Phase 11B — usage_events tenant/time index + usage_daily_workspace rollups.

Revision ID: 0032_usage_daily_workspace
Revises: 0031_audit_logs_retention

``ix_usage_events_workspace_created`` is created CONCURRENTLY so a large
production ``usage_events`` table is not rewrite-locked for the whole
build. CONCURRENTLY cannot run inside a transaction (Alembic
``autocommit_block`` commits prior DDL first). Table/index creates are
idempotent so a retry after a failed concurrent build can finish.

Does **not** partition ``usage_events`` (Phase 11C).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_usage_daily_workspace"
down_revision: str | None = "0031_audit_logs_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLLUP = "usage_daily_workspace"
_DAY_INDEX = "ix_usage_daily_workspace_day"
_EVENTS_INDEX = "ix_usage_events_workspace_created"


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table: str, index: str) -> bool:
    if not _table_exists(table):
        return False
    return any(item["name"] == index for item in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _table_exists(_ROLLUP):
        op.create_table(
            _ROLLUP,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_count", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("billed_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
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
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint(
                "workspace_id",
                "day",
                "api_key_id",
                name="uq_usage_daily_workspace_ws_day_key",
            ),
            sa.CheckConstraint(
                "event_count >= 0",
                name="ck_usage_daily_workspace_event_count_non_negative",
            ),
            sa.CheckConstraint(
                "billed_tokens >= 0",
                name="ck_usage_daily_workspace_billed_non_negative",
            ),
            sa.CheckConstraint(
                "input_tokens >= 0",
                name="ck_usage_daily_workspace_input_non_negative",
            ),
            sa.CheckConstraint(
                "output_tokens >= 0",
                name="ck_usage_daily_workspace_output_non_negative",
            ),
        )
    if not _index_exists(_ROLLUP, _DAY_INDEX):
        op.create_index(_DAY_INDEX, _ROLLUP, ["day"])

    # SHARE lock for a btree build would block writes on a large table.
    # CONCURRENTLY allows reads+writes; cannot run in a transaction.
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        invalid = conn.execute(
            sa.text(
                f"""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_class c
                    JOIN pg_index i ON i.indexrelid = c.oid
                    WHERE c.relname = '{_EVENTS_INDEX}'
                      AND NOT i.indisvalid
                )
                """
            )
        ).scalar()
        if invalid:
            # Failed concurrent builds leave INVALID indexes; IF NOT EXISTS
            # would skip recreating them.
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_EVENTS_INDEX}"))
        conn.execute(
            sa.text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_EVENTS_INDEX} "
                "ON usage_events (workspace_id, created_at DESC)"
            )
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_EVENTS_INDEX}"))
    if _index_exists(_ROLLUP, _DAY_INDEX):
        op.drop_index(_DAY_INDEX, table_name=_ROLLUP)
    if _table_exists(_ROLLUP):
        op.drop_table(_ROLLUP)
