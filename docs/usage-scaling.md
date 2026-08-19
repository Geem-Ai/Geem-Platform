# Usage metering at scale (Phase 11B + 11C)

Geem keeps usage metering in PostgreSQL. Quotas stay O(1). Daily rollups keep
API usage summaries off the raw event heap. Monthly RANGE partitions bound
raw telemetry scans and let retention drop whole months.

## Usage storage layers

1. **`usage_period_counters`**
   - Operational quota state (used / reserved) plus reservation rows
   - O(1) remaining checks
   - Never recomputed from `usage_events` or `usage_daily_workspace`

2. **`usage_events`**
   - Append-only detailed telemetry (AI cost, attribution, tokens, sanitized `cost_metadata`)
   - Partitioned parent: monthly `RANGE (created_at)` (UTC)
   - Hot retention: 13 calendar months (configurable)
   - Source for paginated Workspace / API usage history

3. **`usage_daily_workspace`**
   - Derived UTC-day × workspace × API key rollups
   - Customer API usage period summaries (complete days)

```text
AI/API/ingestion
     ↓
AiUsageService settle  (same transaction as today)
     ├── usage_period_counters     ← quota / O(1)
     └── usage_events              ← partitioned raw telemetry
              ↓
     daily rollup (Celery Beat)
              ↓
     usage_daily_workspace         ← historical API usage summaries
```

| Concern | Source of truth |
|---------|-----------------|
| Quota remaining | `usage_period_counters` + reservations |
| Detailed history | `usage_events` (paginated, tenant/time index, `created_at` bounds) |
| API usage period summary | `usage_daily_workspace` for complete UTC days; bounded raw scan for partial edges (including today) |

## Partition naming

`usage_events_YYYY_MM` — UTC calendar month of `created_at`.

Examples: `usage_events_2026_07`, `usage_events_2026_08`.

## Partition boundaries

Half-open UTC ranges. Never `BETWEEN`.

August 2026:

```text
FROM ('2026-08-01 00:00:00+00')
TO   ('2026-09-01 00:00:00+00')
```

`2026-09-01 00:00:00+00` belongs to September. Timestamps are `timestamptz`;
store and query in UTC. A wall-clock `2026-08-01 00:00+03` is 2026-07-31 UTC
and routes to July.

There is **no DEFAULT partition**. Missing months fail writes loudly so Beat /
startup cannot silently hide a skipped month.

## Partition creation

1. **Alembic `0033_usage_events_partition`** — converts the heap (Phase 11B
   schema) to a partitioned parent, creates every month covering existing
   `MIN(created_at)…MAX(created_at)`, plus the current write window.
2. **API lifespan + Celery worker_ready** — `ensure_write_window()`:
   current UTC month + `USAGE_EVENTS_PARTITIONS_AHEAD_MONTHS` (default **2**,
   so current + next two months). Advisory-locked, idempotent. Not a
   historical backfill.
3. **Beat 00:20 UTC** — same ensure task.

## Retention

`USAGE_EVENTS_RETENTION_MONTHS` (default **13**).

Semantics: **current UTC calendar month plus the previous 12 months**.
If now is August 2026, keep `2025-08` through `2026-08`. Drop `2025-07` and
older by `DROP TABLE usage_events_YYYY_MM` (not `DELETE FROM usage_events`).

Schema conversion **preserves** rows older than 13 months. The first scheduled
retention run after upgrade may drop several expired months.

Current and future partitions are never dropped. Names that do not match
`^usage_events_YYYY_MM$` are ignored.

## Celery Beat

Compose service **`beat`** (already present; not embedded in the worker):

```text
celery -A app.worker.celery_app beat --loglevel=INFO --schedule /tmp/celerybeat-schedule
```

**Exactly one Beat instance** per Compose stack. The schedule file lives in
`/tmp` inside the container so bind-mounts cannot fork two schedulers on the
same file. Do not scale `beat` replicas.

UTC (`enable_utc=True`, `timezone=UTC`):

| Time (UTC) | Task | Behavior |
|------------|------|----------|
| 00:10 | `rollup_usage_daily` | `recent_days=2` — yesterday and the day before (idempotent replace) |
| 00:20 | `ensure_usage_event_partitions` | current + ahead months |
| 00:30 | `retain_usage_event_partitions` | drop expired monthly partitions |

Existing 15-minute attachment/widget purges and 6-hour Drive/OneDrive renewals
remain.

Manual:

```bash
celery -A app.worker.celery_app call rollup_usage_daily
celery -A app.worker.celery_app call rollup_usage_daily --kwargs='{"recent_days":2}'
celery -A app.worker.celery_app call ensure_usage_event_partitions
celery -A app.worker.celery_app call retain_usage_event_partitions
```

## History window

`USAGE_HISTORY_MAX_DAYS` (default **90**) is enforced server-side on
`GET /api/usage/history`. Ranges wider than 90 days return **422**
(`validation`). The range is **not** silently shortened.

When `from` and `to` are both omitted (Workspace **All time**), the API uses
`USAGE_HISTORY_MAX_DAYS` (default **90**) ending at now. When only `to` is
sent, `from` defaults to `to − USAGE_HISTORY_DEFAULT_DAYS` (default **30**).
Ranges wider than `USAGE_HISTORY_MAX_DAYS` return **422** (`validation`);
they are **not** silently shortened.

`GET /api/api-usage/history` stays on the existing `24h` / `7d` / `30d`
sliding windows (already ≤ 90 days) with explicit `created_at` bounds.

Raw data is still retained 13 months; this only bounds each request.

## cost_metadata

Writes go through an allowlist sanitizer (`before_insert`). Unknown keys,
nested objects, secrets, prompts, and provider dumps are dropped.

Accounting (kept when valid primitives): `family`, `model`, `multiplier`,
`raw_prompt_tokens`, `raw_completion_tokens`, `raw_total_tokens`,
`billed_tokens`.

Diagnostics (omitted if oversized): `token_source`, `total_tokens`,
`prompt_version`, `workspace_id`, `expert_id`, `knowledge_workspace_id`,
`expert_type`, `population`, `provider_request_id`, `billing_request_id`,
`chunk_count`, `duration_seconds`, `audio_format`, `byte_size`.

Existing rows are not rewritten by the migration.

## Indexes

| Index | Status |
|-------|--------|
| `PRIMARY KEY (id, created_at)` | partition-compatible (Phase 11C) |
| `ix_usage_events_workspace_created` `(workspace_id, created_at DESC)` | partitioned index (11B, kept on parent) |
| `ix_usage_events_workspace_api_key_created` partial | Phase 7C, kept |
| `ix_credit_ledger_workspace_created` | unchanged |

`messages.usage_event_id` is a **logical UUID**, not a PostgreSQL FK.
Partitioned uniqueness cannot be `(id)` alone. Application-generated UUIDs
remain unique.

## Operations

Inspect partitions:

```sql
SELECT inhrelid::regclass AS partition
FROM pg_inherits
JOIN pg_class p ON p.oid = inhparent
WHERE p.relname = 'usage_events'
ORDER BY 1;
```

Create a missing month (idempotent):

```bash
celery -A app.worker.celery_app call ensure_usage_event_partitions
```

Or from a shell: `UsagePartitionService(db).ensure_month(date(2026, 9, 1))`.

Rerun rollup / retention: Celery `call` as above.

Beat: `docker compose ps beat` and worker logs. Scheduled task names are in
`app.worker.celery_app` `beat_schedule`.

Query pruning:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM usage_events
WHERE workspace_id = $1
  AND created_at >= $2
  AND created_at < $3
ORDER BY created_at DESC
LIMIT 50;
```

Expect only overlapping `usage_events_YYYY_MM` children and
`ix_usage_events_workspace_created`.

## First production upgrade

`docker compose up` runs `alembic upgrade head` on API start. Worker and Beat
wait for the API **healthcheck** (`service_healthy`, `start_period` 180s) so
they do not write `usage_events` while 0033 holds the table. Revision
`0033_usage_events_partition`:

- Builds monthly partitions and secondary indexes on an empty replacement
  table **before** locking
- Takes `ACCESS EXCLUSIVE` on `usage_events` only for the copy + swap + drop
- Preserves every existing row (count-checked)
- Does **not** drop data older than 13 months
- Drops the FK from `messages.usage_event_id`

In-flight writers waiting on the lock can still fail with a stale relation OID
if they already opened the heap; stopping workers until API is healthy avoids
that on Compose upgrades. This is a **hard cutover**, not zero-downtime.

Duration scales with table size (seconds on small DBs; minutes possible at
millions of rows). Writes pause for that window. This is **not** claimed as
zero-downtime. Retry: the revision is transactional; a failed upgrade rolls
back. If the parent is already partitioned, upgrade is a no-op besides
ensuring the write window.

## 1M-event fixture

```bash
cd apps/api
GEEM_USAGE_SCALE=1 pytest -q tests/performance/test_usage_events_scale_phase11b.py
```

## Configuration

| Variable | Default | Notes |
|----------|---------|--------|
| `USAGE_EVENTS_RETENTION_MONTHS` | 13 | 1–60 |
| `USAGE_EVENTS_PARTITIONS_AHEAD_MONTHS` | 2 | 1–12 |
| `USAGE_HISTORY_MAX_DAYS` | 90 | 1–366; omitted `from`+`to` uses this window |
| `USAGE_HISTORY_DEFAULT_DAYS` | 30 | 1–max; used when only `to` is sent |

Malformed integers fail Settings startup with a validation error.

## Phase leftovers (not 11C)

- OTEL / tracing
- Final Playwright / RTL suites
- Extra quota load harness beyond the 1M architecture checks
