# Architecture notes

## Request paths

- Upload: `POST /api/documents` → MinIO + Postgres → Celery `ingest_document`
- Ingest: pypdf page split → OpenRouter mistral-ocr per page → normalize → chunk → embed → Qdrant
- Query: `POST /api/query` → embed → Qdrant top-k → rerank → neighbor expand → chat → validate citation IDs
- Client Agent: `POST /api/v1/agent/chat/completions` → API-key/scope/runtime App admission → Expert-scoped retrieval → raw text or `tool_calls`; the caller executes tools and replays the bounded transcript

## Provider boundaries

Domain code depends on protocols in `app/core/protocols.py` and `app/notifications/` (email). Concrete adapters live under `app/openrouter/`, `app/storage/`, and `app/notifications/`.

## Versions

Pipeline version fields are stored on `documents.processing_version` when a document becomes `ready`.

## Usage scale (Phase 11B + 11C)

- Daily API usage rollups, monthly `usage_events` partitions, Celery Beat: [usage-scaling.md](./usage-scaling.md)
- OpenTelemetry (optional): [observability.md](./observability.md)
- Isolation / quota load harness: [load-testing.md](./load-testing.md)
- Platform Admin host + `platform_role`: [platform-admin.md](./platform-admin.md)
- Paid, stateless client-owned tool loops: [integrations/client-agent-api.md](./integrations/client-agent-api.md)
