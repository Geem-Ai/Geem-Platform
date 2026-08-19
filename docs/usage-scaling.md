# Usage metering at scale (Phase 11B)

Geem keeps usage metering in PostgreSQL. Quotas stay O(1). This slice adds a
Workspace/time index and daily rollups so API usage summaries do not scan
millions of raw `usage_events`.

Phase 11C (not this slice) will add monthly RANGE partitioning, Celery Beat,
partition retention, `cost_metadata` hygiene, and a history max date window.

## Architecture

```text
usage write
     ↓
AiUsageService settle  (same transaction as today)
     ├── usage_period_counters     ← quota / O(1)
     └── usage_events              ← append-only detailed telemetry
              ↓
     daily rollup task (manual in 11B; Beat in 11C)
              ↓
     usage_daily_workspace         ← historical API usage summaries
```

| Concern | Source of truth |
|---------|-----------------|
| Quota remaining | `usage_period_counters` + reservations — **never** SUM of events or rollups |
| Detailed history | `usage_events` (paginated, tenant/time index) |
| API usage period summary | `usage_daily_workspace` for complete UTC days; bounded raw scan for partial edges (including today) |

## Why quotas do not scan `usage_events`

`AiUsageService` reserve/settle updates period counters atomically. Remaining
included tokens are `limit - used - reserved` on those rows. Recalculating from
events would be racy and O(n).

## Why raw events remain

The Usage History UI (and API usage history) lists individual operations,
models, request ids, and credit ledger rows. Rollups cannot reconstruct that.

`usage_events.workspace_id` is nullable (platform / unattributed telemetry).
Those rows are **not** rolled into `usage_daily_workspace`. Internal Workspace
Chat (`api_key_id IS NULL`) is also excluded from the rollup because
`ApiActivityService` only reports API-key attribution.

## Rollup grain

Table: `usage_daily_workspace`

Unique key: `(workspace_id, day, api_key_id)`

`day` is the **UTC calendar date** of `usage_events.created_at`
(`[day 00:00, next day 00:00)` exclusive end). Workspace local timezone is not
used.

Columns: `event_count`, `billed_tokens`, `input_tokens`, `output_tokens`.

`billed_tokens` is the sum of the already-recorded
`cost_metadata.billed_tokens` (fallback: input+output columns). Family
multipliers are **not** applied again.

Family is not a rollup dimension: the API summary groups by API key only.
Detailed family still comes from raw history rows.

## Rerolls and late events

`UsageDailyRollupService.rollup_day` **deletes** that UTC day’s rollup rows,
then `INSERT … SELECT … GROUP BY` from events. Re-running a day matches a
fresh aggregation. Do not add “existing += delta”.

## Current / partial day (API summary)

`GET /api/api-usage/summary` periods (`24h` / `7d` / `30d`) are **sliding
windows** (`now - period`, `now`), not calendar months.

- Complete UTC days fully inside the window → `usage_daily_workspace`
- Partial start/end (including today) → `usage_events` only for those
  timestamp ranges

After deploy, **backfill** completed days or historical summaries will read as
zero until rollup rows exist. Same-day activity still appears without a job.

## Indexes

| Index | Status |
|-------|--------|
| `ix_usage_events_workspace_created` `(workspace_id, created_at DESC)` | **added** in 11B |
| `ix_usage_events_workspace_api_key_created` partial | already present (Phase 7C) |
| `ix_usage_events_workspace_id` | already present (kept; not equivalent to the time composite) |
| `ix_credit_ledger_workspace_created` `(workspace_id, created_at)` | **already present** — not duplicated (btree scans both directions) |

## Backfill

Schema migration does **not** aggregate history. After `alembic upgrade`:

```bash
cd apps/api
python -m app.maintenance.usage_daily_rollup --start 2026-01-01 --end 2026-08-18
python -m app.maintenance.usage_daily_rollup --day 2026-08-18
python -m app.maintenance.usage_daily_rollup --yesterday
```

## Celery task (not Beat)

The worker must import `app.usage.tasks`. **No Beat schedule** in 11B.

```bash
celery -A app.worker.celery_app call rollup_usage_daily
celery -A app.worker.celery_app call rollup_usage_daily --args='["2026-08-18"]'
celery -A app.worker.celery_app call rollup_usage_daily --kwargs='{"start_day":"2026-07-01","end_day":"2026-08-18"}'
```

Default with no dates: **yesterday UTC**.

## 1M-event fixture

```bash
cd apps/api
python -m app.maintenance.seed_usage_scale --events 1000000 \
  --workspace-id <uuid> --workspace-id <uuid> \
  --api-key-id <uuid> --api-key-id <uuid> \
  --start-day 2026-07-20 --days 30

GEEM_USAGE_SCALE=1 pytest -q tests/performance/test_usage_events_scale_phase11b.py
```

Uses `generate_series` bulk insert, not per-row ORM `add()`.

## EXPLAIN (Workspace history)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM usage_events
WHERE workspace_id = $1
  AND created_at >= $2
  AND created_at < $3
ORDER BY created_at DESC
LIMIT 50;
```

Expect an index scan (or bitmap) on `ix_usage_events_workspace_created`.
CI asserts the index name appears in `EXPLAIN (FORMAT JSON)` with
`enable_seqscan = off` (small fixtures otherwise seq-scan). Do not assert
PostgreSQL cost numbers.

## Production locking (migration `0032_usage_daily_workspace`)

- `usage_daily_workspace` is created in the normal Alembic transaction.
  `upgrade()` skips `CREATE TABLE` / the day index if they already exist so a
  retry after a failed concurrent index build can finish (autocommit commits
  that DDL before `CREATE INDEX CONCURRENTLY`).
- `ix_usage_events_workspace_created` uses `CREATE INDEX CONCURRENTLY`
  inside `autocommit_block` so existing rows can still be written during the
  build. Concurrent index creation cannot run inside a transaction; deploy
  must allow Alembic to commit around that statement. An INVALID leftover
  from a failed concurrent build is dropped before recreate.
- First upgrade on a large table may take minutes; it should not take an
  exclusive rewrite lock for the whole build.
- Rollup access uses unique `(workspace_id, day, api_key_id)` plus
  `ix_usage_daily_workspace_day` for per-day replace. There is no extra
  `workspace_id`-only index.

## Phase 11C leftovers

- Monthly RANGE partition of `usage_events`
- Celery Beat: daily rollup, ensure partitions, drop >13 months
- History max date window (~90 days)
- `cost_metadata` allowlist
- Optional more frequent “today” rollup if partial-day raw scans grow
