"""Monthly RANGE partitions for ``usage_events`` (Phase 11C).

Naming: ``usage_events_YYYY_MM`` (UTC calendar month).
Bounds: half-open ``[month_start, next_month_start)``.

There is no DEFAULT partition. Current + N future months are created
proactively so writes never depend on Beat catching up at month boundary.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

PARENT_TABLE = "usage_events"
PARTITION_NAME_RE = re.compile(r"^usage_events_(\d{4})_(\d{2})$")
ADVISORY_KEY_1 = 11
ADVISORY_KEY_2 = 13  # dedicated pair; not a workspace UUID lock


def utc_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def month_start(value: date | datetime) -> date:
    if isinstance(value, datetime):
        value = utc_now(value).date()
    return date(value.year, value.month, 1)


def add_months(start: date, delta: int) -> date:
    """Calendar-month arithmetic on the first of the month."""
    first = month_start(start)
    total = first.year * 12 + (first.month - 1) + delta
    year, month0 = divmod(total, 12)
    return date(year, month0 + 1, 1)


def month_bounds(start: date) -> tuple[datetime, datetime]:
    first = month_start(start)
    nxt = add_months(first, 1)
    return (
        datetime(first.year, first.month, 1, tzinfo=UTC),
        datetime(nxt.year, nxt.month, 1, tzinfo=UTC),
    )


def partition_name_for(start: date) -> str:
    first = month_start(start)
    return f"usage_events_{first.year:04d}_{first.month:02d}"


def parse_partition_name(name: str) -> date | None:
    match = PARTITION_NAME_RE.fullmatch(name)
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    return date(year, month, 1)


def assert_safe_partition_name(name: str) -> str:
    if parse_partition_name(name) is None:
        raise ValueError(f"refusing unsafe usage partition identifier: {name!r}")
    return name


def iter_months(start: date, end_inclusive: date) -> list[date]:
    cursor = month_start(start)
    last = month_start(end_inclusive)
    if last < cursor:
        return []
    months: list[date] = []
    while cursor <= last:
        months.append(cursor)
        cursor = add_months(cursor, 1)
    return months


def retention_cutoff_month(now: datetime | None, retention_months: int) -> date:
    """Oldest month start that is still retained.

    Retention of N months means the current UTC calendar month plus the
    previous N-1 months (N months of hot telemetry including the current
    month). Example: August 2026 with N=13 retains 2025-08 through 2026-08
    and drops 2025-07 and earlier.
    """
    if retention_months < 1:
        raise ValueError("retention_months must be >= 1")
    current = month_start(utc_now(now))
    return add_months(current, -(retention_months - 1))


def _advisory_lock(conn: Connection) -> None:
    conn.execute(
        text("SELECT pg_advisory_xact_lock(:k1, :k2)"),
        {"k1": ADVISORY_KEY_1, "k2": ADVISORY_KEY_2},
    )


def parent_is_partitioned(conn: Connection, table: str = PARENT_TABLE) -> bool:
    kind = conn.execute(
        text(
            """
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = :name
            """
        ),
        {"name": table},
    ).scalar()
    return kind == "p"


def partition_exists(conn: Connection, name: str) -> bool:
    assert_safe_partition_name(name)
    found = conn.execute(
        text(
            """
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = :name
            """
        ),
        {"name": name},
    ).scalar()
    return found is not None


def list_managed_partitions(conn: Connection) -> list[str]:
    rows = conn.execute(
        text(
            """
            SELECT child.relname
            FROM pg_inherits i
            JOIN pg_class child ON child.oid = i.inhrelid
            JOIN pg_class parent ON parent.oid = i.inhparent
            JOIN pg_namespace n ON n.oid = parent.relnamespace
            WHERE n.nspname = current_schema()
              AND parent.relname = :parent
            ORDER BY child.relname
            """
        ),
        {"parent": PARENT_TABLE},
    ).scalars()
    names: list[str] = []
    for raw in rows:
        if parse_partition_name(raw) is not None:
            names.append(raw)
    return names


def create_monthly_partition(
    conn: Connection,
    start: date,
    *,
    parent: str = PARENT_TABLE,
) -> bool:
    """Create one monthly partition. Returns True if created, False if existed."""
    if parent != PARENT_TABLE and parent != "usage_events_parted":
        raise ValueError(f"refusing to partition unexpected parent: {parent!r}")
    name = partition_name_for(start)
    assert_safe_partition_name(name)
    lo, hi = month_bounds(start)
    if partition_exists(conn, name):
        return False
    lo_sql = lo.strftime("%Y-%m-%d %H:%M:%S+00")
    hi_sql = hi.strftime("%Y-%m-%d %H:%M:%S+00")
    conn.execute(
        text(
            f'CREATE TABLE IF NOT EXISTS "{name}" '
            f'PARTITION OF "{parent}" '
            f"FOR VALUES FROM ('{lo_sql}') TO ('{hi_sql}')"
        )
    )
    return True


@dataclass(frozen=True, slots=True)
class EnsureResult:
    checked: list[str]
    created: list[str]
    existing: list[str]


@dataclass(frozen=True, slots=True)
class RetentionResult:
    cutoff: str
    inspected: list[str]
    dropped: list[str]
    skipped: list[str]


class UsagePartitionService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def _conn(self) -> Connection:
        return self.db.connection()

    def ensure_month(self, start: date) -> bool:
        _advisory_lock(self._conn)
        created = create_monthly_partition(self._conn, start)
        name = partition_name_for(start)
        if created:
            logger.info(
                "usage.partitions.created",
                extra={"created_partitions": [name], "checked_months": [name]},
            )
        return created

    def ensure_months(self, months: list[date]) -> EnsureResult:
        _advisory_lock(self._conn)
        checked: list[str] = []
        created: list[str] = []
        existing: list[str] = []
        for month in months:
            name = partition_name_for(month)
            checked.append(name)
            if create_monthly_partition(self._conn, month):
                created.append(name)
            else:
                existing.append(name)
        logger.info(
            "usage.partitions.ensure_done",
            extra={
                "checked_months": checked,
                "created_partitions": created,
                "existing_partitions": existing,
            },
        )
        return EnsureResult(checked=checked, created=created, existing=existing)

    def ensure_write_window(self, *, now: datetime | None = None) -> EnsureResult:
        """Current UTC month plus configured future months (default +2)."""
        current = month_start(utc_now(now))
        ahead = int(self.settings.usage_events_partitions_ahead_months)
        months = [add_months(current, offset) for offset in range(0, ahead + 1)]
        return self.ensure_months(months)

    def ensure_range(self, start: date, end_inclusive: date) -> EnsureResult:
        return self.ensure_months(iter_months(start, end_inclusive))

    def ensure_test_window(self, *, now: datetime | None = None) -> EnsureResult:
        """Wide window so pytest historical timestamps can insert."""
        current = month_start(utc_now(now))
        ahead = int(self.settings.usage_events_partitions_ahead_months)
        start = add_months(current, -24)
        end = add_months(current, ahead)
        return self.ensure_range(start, end)

    def drop_expired(self, *, now: datetime | None = None) -> RetentionResult:
        _advisory_lock(self._conn)
        retention = int(self.settings.usage_events_retention_months)
        cutoff = retention_cutoff_month(now, retention)
        current = month_start(utc_now(now))
        inspected = list_managed_partitions(self._conn)
        dropped: list[str] = []
        skipped: list[str] = []
        for name in inspected:
            start = parse_partition_name(name)
            if start is None:
                skipped.append(name)
                continue
            if start >= current:
                skipped.append(name)
                continue
            if start >= cutoff:
                skipped.append(name)
                continue
            assert_safe_partition_name(name)
            self._conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
            dropped.append(name)
        logger.info(
            "usage.partitions.retention_done",
            extra={
                "retention_cutoff": cutoff.isoformat(),
                "inspected_partitions": inspected,
                "dropped_partitions": dropped,
                "skipped_partitions": skipped,
            },
        )
        return RetentionResult(
            cutoff=cutoff.isoformat(),
            inspected=inspected,
            dropped=dropped,
            skipped=skipped,
        )


def ensure_write_window_on_connection(conn: Connection, settings: Settings) -> EnsureResult:
    """Alembic/startup helper using a raw connection (same lock + DDL)."""
    _advisory_lock(conn)
    current = month_start(utc_now())
    ahead = int(settings.usage_events_partitions_ahead_months)
    months = [add_months(current, offset) for offset in range(0, ahead + 1)]
    created: list[str] = []
    existing: list[str] = []
    checked = [partition_name_for(m) for m in months]
    for month in months:
        name = partition_name_for(month)
        if create_monthly_partition(conn, month):
            created.append(name)
        else:
            existing.append(name)
    return EnsureResult(checked=checked, created=created, existing=existing)


def bootstrap_startup_partitions(db: Session) -> None:
    """Fail loudly if the current month cannot be made writable."""
    try:
        if not parent_is_partitioned(db.connection()):
            logger.warning("usage.partitions.parent_not_partitioned")
            return
        UsagePartitionService(db).ensure_write_window()
        db.commit()
    except ProgrammingError:
        db.rollback()
        raise
