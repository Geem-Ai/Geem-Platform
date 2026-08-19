"""Phase 11B scale fixture — 1M usage_events. Skipped unless GEEM_USAGE_SCALE=1."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.maintenance.seed_usage_scale import seed_usage_events
from app.usage.api_activity import ApiActivityService
from app.usage.models import UsageDailyWorkspace, UsagePeriodCounter
from app.usage.rollup import UsageDailyRollupService
from app.usage.summary import UsageSummaryService
from app.workspaces.service import WorkspaceService

pytestmark = [
    pytest.mark.performance,
    pytest.mark.skipif(
        os.environ.get("GEEM_USAGE_SCALE") != "1",
        reason="set GEEM_USAGE_SCALE=1 to run the 1M-event scale fixture",
    ),
]


def _api_key(db: Session, workspace, actor_id: uuid.UUID, name: str):
    from app.api_keys.service import ApiKeyService

    return ApiKeyService(db).create_key(
        workspace=workspace, actor_id=actor_id, name=name
    ).row


def test_one_million_events_summary_and_history_plans(db: Session, register_user) -> None:
    actors = []
    for label in ("a", "b", "c", "d", "e"):
        user = register_user(email=f"scale-{label}@example.com")
        actors.append(uuid.UUID(user["user"]["id"]))
    workspaces = []
    keys = []
    for slug, actor in zip(
        ("scale-a", "scale-b", "scale-c", "scale-d", "scale-e"),
        actors,
        strict=True,
    ):
        ws, _ = WorkspaceService(db).create_workspace(
            name=slug, slug=slug, created_by=actor
        )
        workspaces.append(ws)
        keys.append(_api_key(db, ws, actor, slug))
    ws_a = workspaces[0]
    start_day = "2026-03-01"
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)

    t0 = time.perf_counter()
    inserted = seed_usage_events(
        db,
        event_count=1_000_000,
        workspace_ids=[ws.id for ws in workspaces],
        api_key_ids=[key.id for key in keys],
        start_day=start_day,
        days=180,
    )
    db.commit()
    seed_ms = int((time.perf_counter() - t0) * 1000)
    assert inserted == 1_000_000

    t1 = time.perf_counter()
    UsageDailyRollupService(db).backfill(
        datetime(2026, 3, 1, tzinfo=UTC).date(),
        datetime(2026, 8, 18, tzinfo=UTC).date(),
    )
    db.commit()
    rollup_ms = int((time.perf_counter() - t1) * 1000)
    rollup_rows = int(
        db.scalar(select(func.count()).select_from(UsageDailyWorkspace)) or 0
    )
    assert rollup_rows > 0

    t2 = time.perf_counter()
    summary = ApiActivityService(db).summarize(ws_a.id, period="30d", now=now)
    summary_ms = int((time.perf_counter() - t2) * 1000)
    assert summary.ai_tokens.billed > 0

    t3 = time.perf_counter()
    history = ApiActivityService(db).history(ws_a.id, period="30d", limit=50)
    history_ms = int((time.perf_counter() - t3) * 1000)
    assert len(history.items) == 50

    db.execute(text("SET LOCAL enable_seqscan = off"))
    july_plan = db.execute(
        text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT id FROM usage_events
            WHERE workspace_id = :ws
              AND created_at >= TIMESTAMP WITH TIME ZONE '2026-07-01 00:00:00+00'
              AND created_at < TIMESTAMP WITH TIME ZONE '2026-08-01 00:00:00+00'
            ORDER BY created_at DESC
            LIMIT 50
            """
        ),
        {"ws": ws_a.id},
    ).scalar()
    july_blob = json.dumps(july_plan)
    assert "Index Scan" in july_blob or "Index Only Scan" in july_blob
    assert "usage_events_2026_03" not in july_blob
    assert "usage_events_2026_07" in july_blob or "2026_07" in july_blob

    # Cross-month: July + August.
    cross_plan = db.execute(
        text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT id FROM usage_events
            WHERE workspace_id = :ws
              AND created_at >= :start
              AND created_at < :end
            ORDER BY created_at DESC
            LIMIT 50
            """
        ),
        {
            "ws": ws_a.id,
            "start": datetime(2026, 7, 1, tzinfo=UTC),
            "end": datetime(2026, 8, 19, tzinfo=UTC),
        },
    ).scalar()
    cross_blob = json.dumps(cross_plan)
    assert "Index Scan" in cross_blob or "Index Only Scan" in cross_blob
    assert "usage_events_2026_03" not in cross_blob
    assert "usage_events_2026_07" in cross_blob or "2026_07" in cross_blob
    assert "usage_events_2026_08" in cross_blob or "2026_08" in cross_blob

    summary_plan = db.execute(
        text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT api_key_id, SUM(billed_tokens)
            FROM usage_daily_workspace
            WHERE workspace_id = :ws
              AND day >= DATE '2026-07-20'
              AND day < DATE '2026-08-19'
            GROUP BY api_key_id
            """
        ),
        {"ws": ws_a.id},
    ).scalar()
    summary_blob = json.dumps(summary_plan)
    assert "usage_daily_workspace" in summary_blob
    assert "Seq Scan on usage_events" not in summary_blob

    UsageSummaryService(db).summarize(ws_a.id)
    monthly_used = UsageSummaryService(db).summarize(ws_a.id).ai_monthly.used
    assert monthly_used == 0
    counters = int(
        db.scalar(
            select(func.count())
            .select_from(UsagePeriodCounter)
            .where(UsagePeriodCounter.workspace_id == ws_a.id)
        )
        or 0
    )
    assert counters == 0

    report = {
        "fixture_events": inserted,
        "workspaces": 5,
        "days": 180,
        "seed_ms": seed_ms,
        "rollup_ms": rollup_ms,
        "rollup_rows": rollup_rows,
        "summary_billed": summary.ai_tokens.billed,
        "summary_ms": summary_ms,
        "history_ms": history_ms,
        "history_plan_uses_index": True,
        "july_pruned": "usage_events_2026_03" not in july_blob,
        "cross_month_pruned": "usage_events_2026_03" not in cross_blob,
    }
    print("PHASE11C_SCALE " + json.dumps(report))
    assert summary_ms < 5_000
    assert history_ms < 5_000
