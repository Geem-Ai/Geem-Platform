# Arabic PDF RAG MVP

Arabic-first PDF RAG on a single Mac Studio host. OpenRouter provides OCR (`mistral-ocr`), embeddings, reranking, and chat. Local stack: FastAPI, Celery, PostgreSQL, Redis, Qdrant, MinIO, React.

## Documentation

- [Local development](docs/development.md)
- [Deploy on aaPanel](docs/deployment.md)
- [Architecture](docs/architecture.md)

## Quick start

```bash
cp .env.example .env
# set OPENROUTER_API_KEY in .env

cd infra
docker compose up -d --build
```

Services:

| Service | URL |
|--------|-----|
| Web UI (legacy MVP) | http://localhost:5173 |
| Workspace UI (Geem SaaS) | http://localhost:5174 |
| API docs | http://localhost:8000/docs |
| API health | http://localhost:8000/api/health/ready |
| MinIO console | http://localhost:9101 (minio / change-me) |
| MinIO API | http://localhost:9100 |

Reserved (not scaffolded yet beyond README placeholders):

- `apps/dashboard_web` — Platform Admin
- `apps/landpage_web` — marketing / landing

Local frontend without Docker:

```bash
# Legacy MVP
cd apps/web && npm install && npm run dev

# Geem Workspace (Phase 0+)
cd apps/workspace_web && npm install && npm run dev
```

## Flow

1. Upload a PDF in the Documents UI (`POST /api/documents`).
2. Worker splits pages with `pypdf` (no text extraction), OCRs each page via OpenRouter file-parser / `mistral-ocr`.
3. Pages are normalized (canonical + search), chunked, embedded, and upserted to Qdrant.
4. Ask questions in Ask view (`POST /api/query`): embed → retrieve top 20 → rerank top 6 → expand neighbors → grounded answer with DB-validated citations.
5. Citation links open `GET /api/documents/{id}/file#page=N`.

## Environment

See [`.env.example`](.env.example). All model IDs are configurable. Never commit real API keys.

## Development (API without Docker for unit tests)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Generate fixtures:

```bash
python tests/fixtures/generate_fixtures.py
```

Golden eval (requires ready documents + OpenRouter key):

```bash
python -m app.eval.run
```

## Reprocess / delete

- `POST /api/documents/{id}/reprocess` with `{"mode":"failed_pages"}` or `{"mode":"full"}`
- `DELETE /api/documents/{id}` removes Qdrant points, DB rows, and the MinIO object

## Troubleshooting

- **ready is 503**: check postgres/redis/qdrant/minio via `docker compose ps` and `/api/health/ready` checks.
- **Upload stuck in queued**: ensure `worker` container is running; check Celery logs.
- **OCR failures**: verify `OPENROUTER_API_KEY`, page concurrency, and OpenRouter credits.
- **Dimension mismatch**: do not mix embedding models in one Qdrant collection; change `QDRANT_COLLECTION` when switching models.

## Non-goals (post-MVP)

Local LLMs, PyMuPDF text extraction, hybrid BM25, Kubernetes, multi-tenancy.
