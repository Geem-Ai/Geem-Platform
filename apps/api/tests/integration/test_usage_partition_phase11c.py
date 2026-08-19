"""Phase 11C — partitioning, retention, Beat, history window."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError, ErrorCategory
from app.db.models import UsageEvent
from app.usage.history import UsageHistoryService, resolve_history_window
from app.usage.models import UsagePeriodCounter
from app.usage.partitions import (
    UsagePartitionService,
    add_months,
    assert_safe_partition_name,
    list_managed_partitions,
    month_start,
    parent_is_partitioned,
    parse_partition_name,
    partition_name_for,
    retention_cutoff_month,
)
from app.usage.summary import UsageSummaryService
from app.workspaces.service import WorkspaceService


def _workspace(db: Session, register_user, email: str, slug: str):
    user = register_user(email=email)
    actor = uuid.UUID(user["user"]["id"])
    ws, _ = WorkspaceService(db).create_workspace(name=slug, slug=slug, created_by=actor)
    return user, ws, actor


def _child(db: Session, event_id: uuid.UUID) -> str:
    return db.execute(
        text("SELECT tableoid::regclass::text FROM usage_events WHERE id = :id"),
        {"id": event_id},
    ).scalar_one()


def test_usage_events_is_range_partitioned(db: Session) -> None:
    assert parent_is_partitioned(db.connection())
    strategy = db.execute(
        text(
            """
            SELECT pg_get_partkeydef(c.oid)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = 'usage_events'
            """
        )
    ).scalar()
    assert strategy is not None
    assert "RANGE" in strategy.upper()
    assert "created_at" in strategy


def test_rows_route_to_monthly_partitions(db: Session, register_user) -> None:
    _, ws, _ = _workspace(db, register_user, "p11c-route@example.com", "p11c-route")
    jan = UsageEvent(
        operation_type="chat",
        workspace_id=ws.id,
        input_tokens=1,
        output_tokens=1,
        created_at=datetime(2026, 1, 15, 12, tzinfo=UTC),
    )
    feb = UsageEvent(
        operation_type="chat",
        workspace_id=ws.id,
        input_tokens=1,
        output_tokens=1,
        created_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    boundary = UsageEvent(
        operation_type="chat",
        workspace_id=ws.id,
        input_tokens=1,
        output_tokens=1,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    tz_row = UsageEvent(
        operation_type="chat",
        workspace_id=ws.id,
        input_tokens=1,
        output_tokens=1,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    db.add_all([jan, feb, boundary, tz_row])
    db.flush()
    assert _child(db, jan.id) == "usage_events_2026_01"
    assert _child(db, feb.id) == "usage_events_2026_02"
    assert _child(db, boundary.id) == "usage_events_2026_03"
    assert _child(db, tz_row.id) == "usage_events_2026_08"


def test_tenant_time_index_on_parent_and_children(db: Session) -> None:
    names = db.execute(
        text(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname LIKE 'ix_usage_events_workspace_created%'
            """
        )
    ).scalars().all()
    assert "ix_usage_events_workspace_created" in names
    child = partition_name_for(month_start(datetime.now(UTC)))
    child_defs = db.execute(
        text(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = current_schema() AND tablename = :t
            """
        ),
        {"t": child},
    ).scalars().all()
    assert any(
        "workspace_id" in (defn or "") and "created_at" in (defn or "")
        for defn in child_defs
    )


def test_ensure_current_and_next_is_idempotent(db: Session) -> None:
    svc = UsagePartitionService(db)
    first = svc.ensure_write_window(now=datetime(2026, 8, 19, tzinfo=UTC))
    second = svc.ensure_write_window(now=datetime(2026, 8, 19, tzinfo=UTC))
    assert "usage_events_2026_08" in first.checked
    assert "usage_events_2026_10" in first.checked
    assert second.created == []
    assert set(second.existing) == set(second.checked)


def test_concurrent_ensure_is_safe(db: Session) -> None:
    maker = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)

    def _run() -> None:
        session = maker()
        try:
            UsagePartitionService(session).ensure_month(datetime(2026, 11, 1).date())
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: _run(), range(2)))
    assert "usage_events_2026_11" in list_managed_partitions(db.connection())


def test_partition_naming_rejects_injection() -> None:
    with pytest.raises(ValueError):
        assert_safe_partition_name("usage_events_2026_08; DROP TABLE users")
    with pytest.raises(ValueError):
        assert_safe_partition_name("usage_events")
    assert parse_partition_name("usage_events_2026_08") == datetime(2026, 8, 1).date()
    assert parse_partition_name("usage_events_2026_13") is None


def test_retention_13_month_boundary(db: Session) -> None:
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    svc = UsagePartitionService(db)
    try:
        svc.ensure_months(
            [
                datetime(2025, 7, 1).date(),
                datetime(2025, 8, 1).date(),
                datetime(2026, 8, 1).date(),
                datetime(2026, 9, 1).date(),
            ]
        )
        db.flush()
        assert retention_cutoff_month(now, 13) == datetime(2025, 8, 1).date()
        result = svc.drop_expired(now=now)
        db.flush()
        names = set(list_managed_partitions(db.connection()))
        assert "usage_events_2025_07" not in names
        assert "usage_events_2025_08" in names
        assert "usage_events_2026_08" in names
        assert "usage_events_2026_09" in names
        assert "usage_events_2025_07" in result.dropped
        assert svc.drop_expired(now=now).dropped == []
    finally:
        svc.ensure_test_window()
        db.flush()


def test_retention_never_drops_unrelated_tables(db: Session) -> None:
    db.execute(text("CREATE TABLE IF NOT EXISTS usage_events_not_a_part (id int)"))
    db.flush()
    UsagePartitionService(db).drop_expired(now=datetime(2026, 8, 19, tzinfo=UTC))
    exists = db.execute(
        text(
            """
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema() AND c.relname = 'usage_events_not_a_part'
            """
        )
    ).scalar()
    assert exists == 1
    db.execute(text("DROP TABLE usage_events_not_a_part"))


def test_history_window_rejected_and_allowed(db: Session, register_user, client) -> None:
    user, ws, _ = _workspace(db, register_user, "p11c-hist@example.com", "p11c-hist")
    db.add(
        UsageEvent(
            operation_type="chat",
            workspace_id=ws.id,
            input_tokens=4,
            output_tokens=6,
            created_at=datetime(2026, 6, 15, tzinfo=UTC),
        )
    )
    db.commit()
    headers = {
        "Authorization": f"Bearer {user['access_token']}",
        "X-Workspace-Id": str(ws.id),
    }
    too_wide = client.get(
        "/api/usage/history?from=2026-01-01T00:00:00Z&to=2026-08-01T00:00:00Z",
        headers=headers,
    )
    assert too_wide.status_code == 422
    assert too_wide.json()["code"] == "validation"
    ok = client.get(
        "/api/usage/history?from=2026-06-01T00:00:00Z&to=2026-06-30T00:00:00Z",
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["total"] >= 1
    other = register_user(email="p11c-hist-b@example.com")
    hijack = client.get(
        "/api/usage/history?from=2026-06-01T00:00:00Z&to=2026-06-30T00:00:00Z",
        headers={
            "Authorization": f"Bearer {other['access_token']}",
            "X-Workspace-Id": str(ws.id),
        },
    )
    assert hijack.status_code in {403, 404}


def test_history_pagination_intact(db: Session, register_user) -> None:
    _, ws, _ = _workspace(db, register_user, "p11c-page@example.com", "p11c-page")
    now = datetime.now(UTC)
    for i in range(12):
        db.add(
            UsageEvent(
                operation_type="chat",
                workspace_id=ws.id,
                input_tokens=i + 1,
                output_tokens=0,
                created_at=now - timedelta(minutes=i),
            )
        )
    db.flush()
    page = UsageHistoryService(db).list_page(ws.id, limit=5, offset=5)
    assert page.limit == 5
    assert page.offset == 5
    assert len(page.items) == 5


def test_history_created_at_bounds_and_pruning(db: Session, register_user) -> None:
    _, ws, _ = _workspace(db, register_user, "p11c-prune@example.com", "p11c-prune")
    start, end = resolve_history_window(
        datetime(2026, 7, 1, tzinfo=UTC),
        datetime(2026, 8, 1, tzinfo=UTC),
        max_days=90,
        default_days=30,
    )
    assert start == datetime(2026, 7, 1, tzinfo=UTC)
    assert end == datetime(2026, 8, 1, tzinfo=UTC)
    omitted_start, omitted_end = resolve_history_window(
        None,
        None,
        max_days=90,
        default_days=30,
        now=datetime(2026, 8, 19, tzinfo=UTC),
    )
    assert omitted_end == datetime(2026, 8, 19, tzinfo=UTC)
    assert omitted_start == datetime(2026, 5, 21, tzinfo=UTC)
    only_to_start, _ = resolve_history_window(
        None,
        datetime(2026, 8, 19, tzinfo=UTC),
        max_days=90,
        default_days=30,
        now=datetime(2026, 8, 19, tzinfo=UTC),
    )
    assert only_to_start == datetime(2026, 7, 20, tzinfo=UTC)
    with pytest.raises(AppError) as exc:
        resolve_history_window(
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
            max_days=90,
            default_days=30,
        )
    assert exc.value.category == ErrorCategory.VALIDATION
    db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = db.execute(
        text(
            """
            EXPLAIN (FORMAT JSON)
            SELECT id FROM usage_events
            WHERE workspace_id = :ws
              AND created_at >= TIMESTAMP WITH TIME ZONE '2026-07-01 00:00:00+00'
              AND created_at < TIMESTAMP WITH TIME ZONE '2026-08-01 00:00:00+00'
            ORDER BY created_at DESC
            LIMIT 50
            """
        ),
        {"ws": ws.id},
    ).scalar()
    blob = str(plan)
    assert "2026_07" in blob or "usage_events_2026_07" in blob
    assert "usage_events_2026_01" not in blob


def test_cost_metadata_sanitizer_on_insert(db: Session, register_user) -> None:
    _, ws, _ = _workspace(db, register_user, "p11c-meta@example.com", "p11c-meta")
    row = UsageEvent(
        operation_type="chat",
        workspace_id=ws.id,
        input_tokens=1,
        output_tokens=1,
        cost_metadata={
            "family": "chat",
            "billed_tokens": 2,
            "secret": "nope",
            "raw_response": {"text": "hello"},
        },
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    assert row.cost_metadata is not None
    assert row.cost_metadata["billed_tokens"] == 2
    assert "secret" not in row.cost_metadata
    assert "raw_response" not in row.cost_metadata


def test_quota_still_uses_period_counters(db: Session, register_user) -> None:
    _, ws, _ = _workspace(db, register_user, "p11c-quota@example.com", "p11c-quota")
    db.add(
        UsageEvent(
            operation_type="chat",
            workspace_id=ws.id,
            input_tokens=50,
            output_tokens=50,
            cost_metadata={"family": "chat", "billed_tokens": 100},
        )
    )
    db.flush()
    summary = UsageSummaryService(db).summarize(ws.id)
    assert summary.ai_monthly.used == 0
    assert int(
        db.scalar(
            select(func.count())
            .select_from(UsagePeriodCounter)
            .where(UsagePeriodCounter.workspace_id == ws.id)
        )
        or 0
    ) == 0


def test_beat_schedule_is_utc_crontab() -> None:
    import app.usage.tasks  # noqa: F401
    from celery.schedules import crontab

    from app.worker.celery_app import celery_app

    assert celery_app.conf.enable_utc is True
    assert str(celery_app.conf.timezone).upper() == "UTC"
    tasks = {entry["task"]: entry for entry in celery_app.conf.beat_schedule.values()}
    assert isinstance(tasks["rollup_usage_daily"]["schedule"], crontab)
    assert tasks["rollup_usage_daily"]["kwargs"]["recent_days"] == 2
    assert isinstance(tasks["ensure_usage_event_partitions"]["schedule"], crontab)
    assert isinstance(tasks["retain_usage_event_partitions"]["schedule"], crontab)
    assert isinstance(tasks["purge_deleted_conversations"]["schedule"], crontab)
    assert isinstance(tasks["purge_deleted_experts"]["schedule"], crontab)
    assert isinstance(tasks["purge_deleted_workspaces"]["schedule"], crontab)
    conv = tasks["purge_deleted_conversations"]["schedule"]
    exp = tasks["purge_deleted_experts"]["schedule"]
    wss = tasks["purge_deleted_workspaces"]["schedule"]
    assert conv.hour == {1} and conv.minute == {0}
    assert exp.hour == {1} and exp.minute == {15}
    assert wss.hour == {1} and wss.minute == {30}
    from app.usage.tasks import (
        ensure_usage_event_partitions,
        retain_usage_event_partitions,
        rollup_usage_daily,
    )

    for task in (
        rollup_usage_daily,
        ensure_usage_event_partitions,
        retain_usage_event_partitions,
    ):
        assert task.max_retries == 3
        assert Exception in (task.autoretry_for or ())


def test_add_months_calendar() -> None:
    assert add_months(datetime(2026, 1, 1).date(), 1) == datetime(2026, 2, 1).date()
    assert add_months(datetime(2026, 12, 1).date(), 1) == datetime(2027, 1, 1).date()
    assert add_months(datetime(2026, 8, 1).date(), -12) == datetime(2025, 8, 1).date()


def test_current_writes_after_partition_schema(db: Session, register_user) -> None:
    _, ws, _ = _workspace(db, register_user, "p11c-write@example.com", "p11c-write")
    row = UsageEvent(operation_type="chat", workspace_id=ws.id, input_tokens=2, output_tokens=3)
    db.add(row)
    db.flush()
    assert db.get(UsageEvent, (row.id, row.created_at)) is not None
