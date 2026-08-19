"""Backfill ``usage_daily_workspace`` from existing ``usage_events``.

Does not run inside Alembic. Bounded to one UTC day per aggregation.

Usage (from apps/api):

  python -m app.maintenance.usage_daily_rollup --day 2026-08-18
  python -m app.maintenance.usage_daily_rollup --start 2026-07-01 --end 2026-08-18
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta

from app.db.session import SessionLocal
from app.usage.rollup import UsageDailyRollupService, parse_iso_day, utc_today

logger = logging.getLogger("geem.maintenance.usage_daily_rollup")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Roll up usage_events into usage_daily_workspace")
    parser.add_argument("--day", help="Single UTC calendar day (YYYY-MM-DD)")
    parser.add_argument("--start", help="Inclusive UTC start day")
    parser.add_argument("--end", help="Inclusive UTC end day")
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Roll up yesterday UTC (default when no dates are given)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.day and (args.start or args.end):
        parser.error("use --day or --start/--end, not both")
    if (args.start and not args.end) or (args.end and not args.start):
        parser.error("--start and --end are required together")

    db = SessionLocal()
    try:
        svc = UsageDailyRollupService(db)
        if args.day:
            results = [svc.rollup_day(parse_iso_day(args.day))]
        elif args.start:
            results = svc.backfill(parse_iso_day(args.start), parse_iso_day(args.end))
        else:
            results = [svc.rollup_day(utc_today() - timedelta(days=1))]
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("usage.rollup.maintenance_failed")
        return 1
    finally:
        db.close()

    print(
        json.dumps(
            [
                {
                    "day": item.day.isoformat(),
                    "rows": item.rows,
                    "event_count": item.event_count,
                    "billed_tokens": item.billed_tokens,
                    "workspaces": item.workspaces,
                }
                for item in results
            ]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
