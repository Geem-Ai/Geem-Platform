# Load and isolation tests (Phase 11D)

Backend concurrency and cross-tenant fail-closed checks. **No real OpenRouter
or other paid provider calls** — fakes/mocks only.

Normal `pytest -q` still runs these files (they are seconds, not the 1M-row
scale suite). Markers let you target or skip them.

## Markers

| Marker | Purpose |
|--------|---------|
| `isolation` | Cross-Workspace HTTP + Qdrant/MinIO/API-key/RBAC harness |
| `load` | Quota races, credits, Chat ContextVar, Celery tenant reset, usage writes |
| `performance` | 1M usage fixture — **skipped** unless `GEEM_USAGE_SCALE=1` |

```bash
cd apps/api
pytest -q -m isolation
pytest -q -m load
pytest -q -m "not performance and not isolation and not load"
GEEM_USAGE_SCALE=1 pytest -q tests/performance/test_usage_events_scale_phase11b.py
```

## What is covered

- Concurrent cross-tenant identifier guesses (Expert, Conversation, API keys, Apps, usage)
- Qdrant `search_expert` defense-in-depth (mixed payloads + concurrent searches)
- MinIO download uses Workspace authorization, not object-key guessing
- API key + `X-Geem-Expert-Id` of another Workspace fails closed; revoked keys fail closed
- Same user in two Workspaces with different dynamic roles
- 20 concurrent AI reservations near quota; idempotent `request_id`; purchased-credit FIFO
- Concurrent fake-provider Chat turns (ContextVar + argument Workspace stay aligned)
- Sequential Celery-style `tenant_context` A then B in one process
- Concurrent `usage_events` inserts into the current month partition

Correctness under concurrency is the gate. Numbers from a laptop test DB are
baselines, not production SLAs.
