"""Phase 11B scale fixture — 1M usage_events. Skipped unless GEEM_USAGE_SCALE=1."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.maintenance.seed_usage_scale import seed_usage_events
from app.usage.api_activity import ApiActivityService
from app.usage.models import UsageDailyWorkspace
from app.usage.rollup import UsageDailyRollupService
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
    user_a = register_user(email="scale-a@example.com")
    user_b = register_user(email="scale-b@example.com")
    actor_a = uuid.UUID(user_a["user"]["id"])
    actor_b = uuid.UUID(user_b["user"]["id"])
    ws_a, _ = WorkspaceService(db).create_workspace(
        name="Scale A", slug="scale-a", created_by=actor_a
    )
    ws_b, _ = WorkspaceService(db).create_workspace(
        name="Scale B", slug="scale-b", created_by=actor_b
    )
    key_a = _api_key(db, ws_a, actor_a, "a")
    key_b = _api_key(db, ws_b, actor_b, "b")
    start_day = "2026-07-20"
    now = datetime(2026, 8, 19, 15, 0, tzinfo=UTC)

    t0 = time.perf_counter()
    inserted = seed_usage_events(
        db,
        event_count=1_000_000,
        workspace_ids=[ws_a.id, ws_b.id],
        api_key_ids=[key_a.id, key_b.id],
        start_day=start_day,
        days=30,
    )
    db.commit()
    seed_ms = int((time.perf_counter() - t0) * 1000)
    assert inserted == 1_000_000

    t1 = time.perf_counter()
    UsageDailyRollupService(db).backfill(
        datetime(2026, 7, 20, tzinfo=UTC).date(),
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
    plan = db.execute(
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
            "start": now - timedelta(days=30),
            "end": now,
        },
    ).scalar()
    plan_blob = json.dumps(plan)
    assert "ix_usage_events_workspace_created" in plan_blob

    report = {
        "fixture_events": inserted,
        "seed_ms": seed_ms,
        "rollup_ms": rollup_ms,
        "rollup_rows": rollup_rows,
        "summary_billed": summary.ai_tokens.billed,
        "summary_ms": summary_ms,
        "history_ms": history_ms,
        "history_plan_uses_index": True,
    }
    print("PHASE11B_SCALE " + json.dumps(report))
    assert summary_ms < 5_000
    assert history_ms < 5_000
