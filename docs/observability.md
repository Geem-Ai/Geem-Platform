# Observability (Phase 11D)

Geem traces FastAPI, Celery, and selected domain operations with **optional**
OpenTelemetry. Billing truth stays in PostgreSQL (`usage_period_counters`,
`usage_events`, credit ledger). Traces are diagnostics only.

## Enable / disable

| Variable | Default | Meaning |
|----------|---------|---------|
| `OTEL_ENABLED` | `false` | Master switch. When false, no TracerProvider, no OTLP exporter, no library instrumentors. |
| `OTEL_SERVICE_NAME` | `geem-api` | Resource `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | empty | OTLP HTTP traces endpoint (collector). Empty + enabled in local/test: spans exist in-process but are not exported. Non-local + enabled **requires** this URL. |
| `OTEL_EXPORTER_OTLP_HEADERS` | empty | Comma-separated `key=value` pairs (collector auth). **Do not commit production tokens.** |
| `OTEL_TRACES_SAMPLER` | `parentbased_traceidratio` | `parentbased_traceidratio`, `traceidratio`, `always_on`, `always_off` |
| `OTEL_TRACES_SAMPLER_ARG` | `0.1` | Ratio 0–1 for ratio samplers (10% is a production-compatible default) |

Local Compose does **not** run a collector. Point `OTEL_EXPORTER_OTLP_ENDPOINT`
at an external collector when you want export.

## Correlation

| Field | Source |
|-------|--------|
| `X-Request-Id` | Incoming header if it matches `[A-Za-z0-9._-]{1,128}`; otherwise a new UUID. Echoed on the response. |
| `request.id` / logs `request_id` | Same value via `RequestContext` |
| `trace_id` / `span_id` | Current OpenTelemetry span (JSON logs when a valid span exists) |
| `workspace.id` | Backend-authorized Workspace only (session membership or API key). Never a client-supplied name. |
| Celery `task_id` | Task request id (also used as worker `request_id` in tenant context) |

Callers cannot inject oversized or whitespace request IDs into logs.

## Span names (cardinality)

Span **names** are stable operations, not entity IDs or prompts.

Good: `chat.turn`, `rag.retrieve`, `rag.rerank`, `document.ingest`,
`workspace.purge`, `qdrant.search`, `minio.get`, `openrouter.chat`,
`usage.reserve`, `connector.sync`.

Bad: conversation UUID, user prompt, full URL with query string as the name.

IDs (`workspace.id`, `expert_id`, `request.id`) are **attributes**.

## Forbidden in spans and structured logs

Do not record: Authorization headers, cookies, JWTs, API key secrets,
passwords, invitation tokens, raw user prompts, raw model responses,
uploaded document bytes, connector credentials.

HTTP instrumentors are configured not to capture request/response headers.

Provider HTTP exceptions are logged without dumping headers or full bodies.

## What is instrumented

When `OTEL_ENABLED=true`:

- FastAPI (route template as the HTTP span; health/docs excluded)
- Celery (worker process init)
- SQLAlchemy, httpx, Redis (standard instrumentors)
- Manual spans around Chat, Expert query, RAG retrieve/rerank, ingest,
  billing fulfill, connector sync, OpenRouter, Qdrant, MinIO, OpenWA send,
  usage reserve/settle, lifecycle purge

## Celery

Trace context propagates when Celery instrumentation is on (HTTP → ingest /
connector / purge). Tasks still pass explicit `workspace_id` arguments;
`tenant_context` binds and **clears** ContextVars so worker reuse cannot leak
tenancy.

Maintenance Beat (UTC):

| Time | Task |
|------|------|
| 00:10 | `rollup_usage_daily` |
| 00:20 | `ensure_usage_event_partitions` |
| 00:30 | `retain_usage_event_partitions` |
| 01:00 | `purge_deleted_conversations` |
| 01:15 | `purge_deleted_experts` |
| 01:30 | `purge_deleted_workspaces` |

## Tests

```bash
cd apps/api
pytest -q tests/unit/test_observability_phase11d.py
```

Tests use an in-memory span exporter (`configure_test_tracing`). They do not
open OTLP sockets.
