"""Phase 11B — daily usage rollups, summary cutover, history index path."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import UsageEvent
from app.usage.api_activity import (
    ApiActivityService,
    _Window,
    split_usage_window,
)
from app.usage.history import UsageHistoryService
from app.usage.models import UsageDailyWorkspace, UsagePeriodCounter
from app.usage.rollup import UsageDailyRollupService, utc_today
from app.usage.summary import UsageSummaryService
from app.workspaces.service import WorkspaceService


def _event(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    billed: int,
    created_at: datetime,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    multiplier: int = 1,
    family: str = "chat",
    operation_type: str = "chat",
) -> UsageEvent:
    inp = billed // 2 if input_tokens is None else input_tokens
    out = billed - inp if output_tokens is None else output_tokens
    row = UsageEvent(
        operation_type=operation_type,
        model="test-model",
        input_tokens=inp,
        output_tokens=out,
        cost_metadata={
            "family": family,
            "multiplier": multiplier,
            "billed_tokens": billed,
        },
        workspace_id=workspace_id,
        api_key_id=api_key_id,
        created_at=created_at,
    )
    db.add(row)
    return row


def _workspace(db: Session, register_user, email: str, slug: str):
    user = register_user(email=email)
    actor = uuid.UUID(user["user"]["id"])
    ws, _ = WorkspaceService(db).create_workspace(
        name=slug, slug=slug, created_by=actor
    )
    return user, ws, actor


def _api_key(db: Session, workspace, actor_id: uuid.UUID, name: str = "k"):
    from app.api_keys.service import ApiKeyService

    created = ApiKeyService(db).create_key(
        workspace=workspace, actor_id=actor_id, name=name
    )
    return created.row


def test_split_window_30d_has_complete_days_and_partials() -> None:
    end = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    start = end - timedelta(days=30)
    parts = split_usage_window(_Window(key="30d", start=start, end=end))
    assert parts.partial_ranges[0][0] == start
    assert parts.complete_days[0].isoformat() == "2026-07-21"
    assert parts.complete_days[-1].isoformat() == "2026-08-18"
    assert parts.partial_ranges[-1] == (
        datetime(2026, 8, 19, tzinfo=UTC),
        end,
    )


def test_split_window_exact_utc_day() -> None:
    start = datetime(2026, 8, 18, tzinfo=UTC)
    end = datetime(2026, 8, 19, tzinfo=UTC)
    parts = split_usage_window(_Window(key="1d", start=start, end=end))
    assert parts.complete_days == (start.date(),)
    assert parts.partial_ranges == ()


def test_rollup_matches_raw_and_is_idempotent(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-r1@example.com", "p11b-r1")
    key = _api_key(db, ws, actor, "prod")
    day = utc_today() - timedelta(days=2)
    start = datetime(day.year, day.month, day.day, 10, tzinfo=UTC)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=40, created_at=start)
    _event(
        db,
        workspace_id=ws.id,
        api_key_id=key.id,
        billed=15,
        created_at=start + timedelta(hours=1),
        family="embed",
        operation_type="embedding",
    )
    db.flush()
    svc = UsageDailyRollupService(db)
    first = svc.rollup_day(day)
    second = svc.rollup_day(day)
    assert first.billed_tokens == 55
    assert second.billed_tokens == 55
    assert first.rows == second.rows == 1
    rows = db.scalars(
        select(UsageDailyWorkspace).where(UsageDailyWorkspace.day == day)
    ).all()
    assert len(rows) == 1
    assert rows[0].billed_tokens == 55
    assert rows[0].event_count == 2
    assert rows[0].input_tokens + rows[0].output_tokens == 55


def test_no_duplicate_rows_two_keys(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-r2@example.com", "p11b-r2")
    a = _api_key(db, ws, actor, "a")
    b = _api_key(db, ws, actor, "b")
    day = utc_today() - timedelta(days=3)
    at = datetime(day.year, day.month, day.day, 8, tzinfo=UTC)
    _event(db, workspace_id=ws.id, api_key_id=a.id, billed=10, created_at=at)
    _event(db, workspace_id=ws.id, api_key_id=b.id, billed=7, created_at=at)
    db.flush()
    UsageDailyRollupService(db).rollup_day(day)
    rows = db.scalars(
        select(UsageDailyWorkspace).where(
            UsageDailyWorkspace.workspace_id == ws.id,
            UsageDailyWorkspace.day == day,
        )
    ).all()
    assert {row.api_key_id: row.billed_tokens for row in rows} == {a.id: 10, b.id: 7}


def test_workspace_isolation_in_rollups(db: Session, register_user) -> None:
    _, ws_a, actor_a = _workspace(db, register_user, "11b-ia@example.com", "p11b-ia")
    _, ws_b, actor_b = _workspace(db, register_user, "11b-ib@example.com", "p11b-ib")
    key_a = _api_key(db, ws_a, actor_a, "a")
    key_b = _api_key(db, ws_b, actor_b, "b")
    day = utc_today() - timedelta(days=4)
    at = datetime(day.year, day.month, day.day, 9, tzinfo=UTC)
    _event(db, workspace_id=ws_a.id, api_key_id=key_a.id, billed=50, created_at=at)
    _event(db, workspace_id=ws_b.id, api_key_id=key_b.id, billed=80, created_at=at)
    db.flush()
    UsageDailyRollupService(db).rollup_day(day)
    a_sum = db.scalar(
        select(func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0)).where(
            UsageDailyWorkspace.workspace_id == ws_a.id
        )
    )
    b_sum = db.scalar(
        select(func.coalesce(func.sum(UsageDailyWorkspace.billed_tokens), 0)).where(
            UsageDailyWorkspace.workspace_id == ws_b.id
        )
    )
    assert int(a_sum or 0) == 50
    assert int(b_sum or 0) == 80


def test_billed_tokens_not_re_multiplied(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-m@example.com", "p11b-m")
    key = _api_key(db, ws, actor)
    day = utc_today() - timedelta(days=2)
    at = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
    _event(
        db,
        workspace_id=ws.id,
        api_key_id=key.id,
        billed=10,
        input_tokens=5,
        output_tokens=0,
        multiplier=2,
        created_at=at,
    )
    db.flush()
    result = UsageDailyRollupService(db).rollup_day(day)
    assert result.billed_tokens == 10


def test_zero_usage_day_has_no_rows(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-z@example.com", "p11b-z")
    _api_key(db, ws, actor)
    day = utc_today() - timedelta(days=9)
    result = UsageDailyRollupService(db).rollup_day(day)
    assert result.rows == 0
    assert result.billed_tokens == 0


def test_utc_day_boundary(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-utc@example.com", "p11b-utc")
    key = _api_key(db, ws, actor)
    day = utc_today() - timedelta(days=5)
    before = datetime(day.year, day.month, day.day, tzinfo=UTC) - timedelta(
        microseconds=1
    )
    on = datetime(day.year, day.month, day.day, tzinfo=UTC)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=3, created_at=before)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=9, created_at=on)
    db.flush()
    result = UsageDailyRollupService(db).rollup_day(day)
    assert result.billed_tokens == 9


def test_late_event_reroll_updates_totals(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-late@example.com", "p11b-late")
    key = _api_key(db, ws, actor)
    day = utc_today() - timedelta(days=2)
    at = datetime(day.year, day.month, day.day, 4, tzinfo=UTC)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=4, created_at=at)
    db.flush()
    svc = UsageDailyRollupService(db)
    assert svc.rollup_day(day).billed_tokens == 4
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=6, created_at=at)
    db.flush()
    assert svc.rollup_day(day).billed_tokens == 10


def test_null_workspace_and_internal_chat_excluded(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-nt@example.com", "p11b-nt")
    key = _api_key(db, ws, actor)
    day = utc_today() - timedelta(days=2)
    at = datetime(day.year, day.month, day.day, 5, tzinfo=UTC)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=11, created_at=at)
    _event(db, workspace_id=ws.id, api_key_id=None, billed=999, created_at=at)
    _event(db, workspace_id=None, api_key_id=key.id, billed=777, created_at=at)
    db.flush()
    result = UsageDailyRollupService(db).rollup_day(day)
    assert result.billed_tokens == 11


def test_summary_today_without_rollup_matches_raw(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-today@example.com", "p11b-today")
    key = _api_key(db, ws, actor)
    now = datetime.now(UTC)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=22, created_at=now - timedelta(seconds=1))
    db.flush()
    body = ApiActivityService(db).summarize(ws.id, period="24h", now=now)
    assert body.ai_tokens.billed == 22
    by_id = {item.api_key_id: item.billed_tokens for item in body.keys}
    assert by_id[key.id] == 22


def test_completed_day_summary_uses_rollup_not_raw_scan(
    db: Session, register_user
) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-hist@example.com", "p11b-hist")
    key = _api_key(db, ws, actor)
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)
    past = now - timedelta(days=5)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=33, created_at=past)
    db.flush()
    before = ApiActivityService(db).summarize(ws.id, period="30d", now=now)
    assert before.ai_tokens.billed == 0
    UsageDailyRollupService(db).rollup_day(past.date())
    after = ApiActivityService(db).summarize(ws.id, period="30d", now=now)
    assert after.ai_tokens.billed == 33
    by_id = {item.api_key_id: item.billed_tokens for item in after.keys}
    assert by_id[key.id] == 33


def test_multi_day_summary_equals_raw_semantics(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-md@example.com", "p11b-md")
    key = _api_key(db, ws, actor)
    now = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    d1 = now - timedelta(days=3)
    d2 = now - timedelta(days=1)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=10, created_at=d1)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=6, created_at=d2)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=2, created_at=now - timedelta(seconds=1))
    db.flush()
    svc = UsageDailyRollupService(db)
    svc.rollup_day(d1.date())
    svc.rollup_day(d2.date())
    body = ApiActivityService(db).summarize(ws.id, period="7d", now=now)
    assert body.ai_tokens.billed == 18


def test_history_still_raw_and_workspace_isolated(db: Session, register_user) -> None:
    _, ws_a, actor_a = _workspace(db, register_user, "11b-ha@example.com", "p11b-ha")
    _, ws_b, actor_b = _workspace(db, register_user, "11b-hb@example.com", "p11b-hb")
    key_a = _api_key(db, ws_a, actor_a, "a")
    key_b = _api_key(db, ws_b, actor_b, "b")
    now = datetime.now(UTC)
    ev = _event(db, workspace_id=ws_a.id, api_key_id=key_a.id, billed=5, created_at=now)
    _event(db, workspace_id=ws_b.id, api_key_id=key_b.id, billed=9, created_at=now)
    db.flush()
    page = ApiActivityService(db).history(ws_a.id, period="24h")
    assert page.total == 1
    assert page.items[0].id == ev.id
    assert page.items[0].billed_tokens == 5
    hijack = ApiActivityService(db).history(ws_a.id, period="24h", api_key_id=key_b.id)
    assert hijack.items == []
    usage_page = UsageHistoryService(db).list_page(ws_a.id, limit=50)
    assert any(item.id == ev.id for item in usage_page.items)


def test_quotas_still_read_period_counters(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-q@example.com", "p11b-q")
    key = _api_key(db, ws, actor)
    now = datetime.now(UTC)
    _event(db, workspace_id=ws.id, api_key_id=key.id, billed=100, created_at=now - timedelta(seconds=1))
    db.flush()
    summary = UsageSummaryService(db).summarize(ws.id)
    assert summary.ai_monthly.used == 0
    assert db.scalar(select(func.count()).select_from(UsagePeriodCounter)) == 0
    api = ApiActivityService(db).summarize(ws.id, period="24h", now=now)
    assert api.ai_tokens.billed == 100
    assert api.workspace_ai_monthly.used == 0


def test_workspace_created_index_exists(db: Session) -> None:
    name = db.scalar(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'usage_events' "
            "AND indexname = 'ix_usage_events_workspace_created'"
        )
    )
    assert name == "ix_usage_events_workspace_created"
    credit = db.scalar(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'credit_ledger_entries' "
            "AND indexname = 'ix_credit_ledger_workspace_created'"
        )
    )
    assert credit == "ix_credit_ledger_workspace_created"


def test_history_query_can_use_workspace_created_index(db: Session, register_user) -> None:
    _, ws, actor = _workspace(db, register_user, "11b-ex@example.com", "p11b-ex")
    key = _api_key(db, ws, actor)
    now = datetime.now(UTC)
    for i in range(20):
        _event(
            db,
            workspace_id=ws.id,
            api_key_id=key.id,
            billed=1,
            created_at=now - timedelta(minutes=i),
        )
    db.flush()
    db.execute(text("SET LOCAL enable_seqscan = off"))
    plan_row = db.execute(
        text(
            """
            EXPLAIN (FORMAT JSON)
            SELECT id FROM usage_events
            WHERE workspace_id = :ws
              AND created_at >= :start
              AND created_at < :end
            ORDER BY created_at DESC
            LIMIT 50
            """
        ),
        {
            "ws": ws.id,
            "start": now - timedelta(days=1),
            "end": now + timedelta(seconds=1),
        },
    ).scalar()
    blob = json.dumps(plan_row)
    assert "ix_usage_events_workspace_created" in blob


def test_celery_task_is_registered() -> None:
    import app.usage.tasks  # noqa: F401 — register on the shared Celery app
    from app.worker.celery_app import celery_app

    assert "rollup_usage_daily" in celery_app.tasks
    assert "rollup_usage_daily" not in {
        entry.get("task") for entry in celery_app.conf.beat_schedule.values()
    }
