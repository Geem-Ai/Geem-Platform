"""Bulk-insert a large usage_events fixture for scale tests (Phase 11B).

Not invoked by normal pytest. From apps/api:

  python -m app.maintenance.seed_usage_scale --events 1000000 \\
      --workspace-id <uuid> --workspace-id <uuid> \\
      --api-key-id <uuid> --api-key-id <uuid>

Rows are inserted with ``generate_series`` (no per-row ORM add).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid

from datetime import date, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import Integer, String, Text

from app.db.session import SessionLocal
from app.usage.partitions import UsagePartitionService, month_start

logger = logging.getLogger("geem.maintenance.seed_usage_scale")

_FAMILIES = ("chat", "embed", "rerank", "ocr", "title")
_OPS = ("chat", "embedding", "rerank", "pdf_parse", "title")


def seed_usage_events(
    db,
    *,
    event_count: int,
    workspace_ids: list[uuid.UUID],
    api_key_ids: list[uuid.UUID],
    start_day: str,
    days: int,
) -> int:
    if event_count < 1:
        raise ValueError("event_count must be >= 1")
    if not workspace_ids or not api_key_ids:
        raise ValueError("workspace_ids and api_key_ids are required")
    if days < 1:
        raise ValueError("days must be >= 1")
    start = date.fromisoformat(start_day)
    end = start + timedelta(days=days - 1)
    UsagePartitionService(db).ensure_range(month_start(start), month_start(end))
    stmt = text(
        """
        INSERT INTO usage_events (
            id,
            operation_type,
            model,
            input_tokens,
            output_tokens,
            cost_metadata,
            workspace_id,
            api_key_id,
            created_at
        )
        SELECT
            gen_random_uuid(),
            p.ops[1 + ((g - 1) % CARDINALITY(p.ops))],
            'scale-fixture',
            8,
            12,
            jsonb_build_object(
                'family', p.families[1 + ((g - 1) % CARDINALITY(p.families))],
                'multiplier', 1,
                'raw_prompt_tokens', 8,
                'raw_completion_tokens', 12,
                'raw_total_tokens', 20,
                'billed_tokens', 20
            ),
            p.workspaces[1 + ((g - 1) % CARDINALITY(p.workspaces))],
            p.keys[1 + ((g - 1) % CARDINALITY(p.keys))],
            (:start_day)::date::timestamp AT TIME ZONE 'UTC'
                + (((g - 1) % :days) * INTERVAL '1 day')
                + ((g % 86400) * INTERVAL '1 second')
        FROM generate_series(1, :event_count) AS g
        CROSS JOIN (
            SELECT
                CAST(:workspace_ids AS uuid[]) AS workspaces,
                CAST(:api_key_ids AS uuid[]) AS keys,
                CAST(:ops AS text[]) AS ops,
                CAST(:families AS text[]) AS families
        ) AS p
        """
    ).bindparams(
        bindparam("workspace_ids", type_=ARRAY(PG_UUID(as_uuid=True))),
        bindparam("api_key_ids", type_=ARRAY(PG_UUID(as_uuid=True))),
        bindparam("ops", type_=ARRAY(Text())),
        bindparam("families", type_=ARRAY(Text())),
        bindparam("start_day", type_=String()),
        bindparam("days", type_=Integer()),
        bindparam("event_count", type_=Integer()),
    )
    db.execute(
        stmt,
        {
            "event_count": event_count,
            "workspace_ids": workspace_ids,
            "api_key_ids": api_key_ids,
            "start_day": start_day,
            "days": days,
            "ops": list(_OPS),
            "families": list(_FAMILIES),
        },
    )
    return event_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bulk-insert usage_events for scale tests")
    parser.add_argument("--events", type=int, default=1_000_000)
    parser.add_argument("--workspace-id", action="append", dest="workspace_ids", required=True)
    parser.add_argument("--api-key-id", action="append", dest="api_key_ids", required=True)
    parser.add_argument("--start-day", default="2026-07-01")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    workspaces = [uuid.UUID(item) for item in args.workspace_ids]
    keys = [uuid.UUID(item) for item in args.api_key_ids]

    db = SessionLocal()
    started = time.perf_counter()
    try:
        inserted = seed_usage_events(
            db,
            event_count=args.events,
            workspace_ids=workspaces,
            api_key_ids=keys,
            start_day=args.start_day,
            days=args.days,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("usage.scale.seed_failed")
        return 1
    finally:
        db.close()

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(json.dumps({"inserted": inserted, "elapsed_ms": elapsed_ms}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
