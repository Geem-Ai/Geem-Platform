# Geem

Arabic-first AI workspace. Tenants create **Experts**, attach knowledge (PDF / TXT / Markdown), and chat with grounded answers and citations.

Product-facing names, OpenAPI title, and UI strings use **Geem**. Brand: [geem.ai](https://geem.ai). GitHub: [Geem-Ai/Geem-Platform](https://github.com/Geem-Ai/Geem-Platform).

Stack: FastAPI, Celery, PostgreSQL, Redis, Qdrant, MinIO, React. OpenRouter provides OCR (`mistral-ocr`), embeddings, reranking, and chat.

## Status

Phases **0–8** of the multi-tenant SaaS plan are complete (through Workspace Storage inventory). Phase 9 is App Store foundations.

| Ready                                                                                                    | Not yet                                   |
| -------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Auth, workspaces, memberships                                                                            | Platform Admin SPA (`apps/dashboard_web`) |
| Tenant-scoped documents + Expert RAG                                                                     | Marketing site (`apps/landpage_web`)      |
| Conversations + streaming Chat                                                                           | App Store                                 |
| Plans, entitlements, usage meters, quotas                                                                |                                           |
| Billing checkout + Workspace billing UI                                                                  |                                           |
| OpenAI-compatible `POST /api/v1/chat/completions` + `GET /api/v1/models` (Expert via `X-Geem-Expert-Id`) |                                           |
| Workspace Storage inventory (`/storage`) — download + full purge                                         |                                           |

Canonical plan: [`.cursor/plans/multi-tenant_saas_plan_e28c049c.plan.md`](.cursor/plans/multi-tenant_saas_plan_e28c049c.plan.md).

## Documentation

- [Local development](docs/development.md) — Compose, host-run API, auth/CORS, tests
- [Deploy on aaPanel](docs/deployment.md)
- [Architecture](docs/architecture.md)
- [Alembic](apps/api/migrations/README.md)

## Repo layout

| Path                       | Role                                                        |
| -------------------------- | ----------------------------------------------------------- |
| `apps/api`                 | FastAPI + Celery                                            |
| `apps/workspace_web`       | Geem Workspace SPA (port **5174**)                          |
| `apps/dashboard_web`       | Platform Admin SPA (port **5175**; UAT `admin-uat.geem.ai`) |
| `apps/landpage_web`        | Marketing — placeholder only                                |
| `infra/docker-compose.yml` | Local full stack                                            |

`samples/` is a **gitignored, read-only** UI reference (Metronic AI Concept). Production code must not import from or mutate it. Ports into `workspace_web` are listed in [`apps/workspace_web/METRONIC_PORT.md`](apps/workspace_web/METRONIC_PORT.md).

## Quick start

```bash
cp .env.example .env
# set OPENROUTER_API_KEY (and optionally BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD)

cp apps/workspace_web/.env.example apps/workspace_web/.env

cd infra
./scripts/dev-up.sh
# or: docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

| Service       | URL                                             |
| ------------- | ----------------------------------------------- |
| Workspace UI  | <http://localhost:5174>                         |
| API docs      | <http://localhost:8000/docs>                    |
| API ready     | <http://localhost:8000/api/health/ready>        |
| MinIO console | <http://localhost:9101> (`minio` / `change-me`) |

Keep `AUTH_REQUIRED=true` and `LEGACY_MVP_WRITES_ENABLED=false`. Document, query, and job APIs require a logged-in Workspace user.

First admin (optional; or register in the UI):

```bash
cd infra
docker compose --env-file ../.env exec api python -m app.identity.bootstrap
```

Local billing checkout uses the **Noop** gateway when `APP_ENV=local` / `test`. ClickPay credentials are optional until a ClickPay config is enabled.

Tenant-subdomain DX (`*.geem.dm`), Cloudflare Tunnel UAT (`app-uat.geem.ai` / `api-uat.geem.ai` / `landpage-uat.geem.ai` / `admin-uat.geem.ai`), and host-run API/UI are documented in [development.md](docs/development.md).

## Product flow

1. Register or bootstrap an admin; create or join a Workspace.
2. Create an **Expert** (or use **Geem General**, the platform general-knowledge Expert).
3. Upload knowledge (PDF / TXT / MD). The worker OCRs PDFs via OpenRouter, then normalizes, chunks, embeds, and upserts to Qdrant scoped by workspace + Expert.
4. Chat with the Expert (`POST /api/conversations/...`): retrieve → rerank → grounded answer with DB-validated citations. General-mode Experts skip RAG.
5. Usage meters and quotas (AI tokens, Expert slots, storage) are enforced server-side and shown at `/billing/usage`.

Legacy unauthenticated `document_ids` Ask is retired. Product query requires `expert_id`.

## Environment

See [`.env.example`](.env.example) and [`apps/workspace_web/.env.example`](apps/workspace_web/.env.example). All model IDs are configurable. Never commit real API keys.

Required for a working local stack:

- `OPENROUTER_API_KEY`
- `JWT_SECRET` — the example value is fine only when `APP_ENV=local`

## Development

API unit tests (no Docker):

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Workspace UI without Docker:

```bash
cd apps/workspace_web
npm install
npm run dev
```

```bash
npm test
npm run typecheck
```

Generate PDF fixtures / golden eval (needs ready documents + OpenRouter):

```bash
cd apps/api
python tests/fixtures/generate_fixtures.py
python -m app.eval.run
```

## Troubleshooting

- **ready is 503**: `docker compose ps` and `/api/health/ready` checks for postgres / redis / qdrant / minio.
- **Upload stuck in queued**: worker container must be running (`docker compose logs -f worker`).
- **OCR / chat failures**: `OPENROUTER_API_KEY`, credits, and `checks.openrouter` on ready.
- **Login works, refresh fails**: SPA origin vs API host; refresh cookie is host-only on the API host; `CORS_ORIGINS` must list the SPA origin.
- **Embedding dimension mismatch**: do not mix embedding models in one Qdrant collection; change `QDRANT_COLLECTION` when switching models.

## License

Proprietary. Metronic sample source is not committed; obtain it from your Metronic license if you need the UI reference.
