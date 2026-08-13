# Local development

How to run **Geem** on a developer machine. Product UI is `apps/workspace_web`. The API, Celery worker, PostgreSQL, Redis, Qdrant, and MinIO live under `infra/docker-compose.yml`.

For production / aaPanel, see [deployment.md](./deployment.md). Architecture notes: [architecture.md](./architecture.md).

## Prerequisites

| Tool | Version |
|------|---------|
| Docker Desktop (or Docker Engine + Compose v2) | current |
| Node.js | 22.x (workspace UI) |
| Python | 3.12 (API tests / host-run API) |
| OpenRouter API key | required for OCR, embeddings, rerank, and chat. Each family is billed into the Workspace AI token pool using `AI_TOKEN_MULTIPLIER_*` (OCR defaults to 3×). |

Optional for tenant-subdomain DX (`*.geem.dm`): `dnsmasq` or extra `/etc/hosts` entries.

You do **not** need the Metronic sample under `samples/` to run the stack. That tree is a read-only UI reference and is gitignored.

## Repo layout (what you actually run)

| Path | Role |
|------|------|
| `apps/api` | FastAPI + Celery |
| `apps/workspace_web` | Geem Workspace SPA (port **5174**) |
| `apps/web` | Legacy MVP UI (port **5173**) — keep runnable; not the product |
| `apps/dashboard_web` / `apps/landpage_web` | Placeholders only — do not implement |
| `infra/docker-compose.yml` | Local full stack |
| `.env` | API / worker / shared backend env (copy from `.env.example`) |
| `apps/workspace_web/.env` | Vite env (copy from `apps/workspace_web/.env.example`) |

## Environment files

From the repo root:

```bash
cp .env.example .env
cp apps/workspace_web/.env.example apps/workspace_web/.env
```

Set at least:

- `OPENROUTER_API_KEY` in `.env`
- `JWT_SECRET` — the example value is fine **only** when `APP_ENV=local`. Non-local processes refuse weak secrets.
- `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` if you want a first login without using the public register endpoint

Keep `AUTH_REQUIRED=true` and `LEGACY_MVP_WRITES_ENABLED=false`. Document / Query / Jobs require a logged-in Workspace user.

Local billing checkout (Phase 6A/6B) uses the **Noop** gateway automatically when `APP_ENV=local`/`test`. After payment verification the API redirects browsers (`Accept: text/html`) to `WORKSPACE_WEB_URL` (`/billing/payment/success|failed|pending?purchase=…`). Empty `WORKSPACE_WEB_URL` falls back to `http://localhost:5174` only in local/test; in production it disables the HTML redirect instead of sending users to localhost. The SPA re-fetches the purchase; it does not trust provider query parameters. ClickPay credentials (`CLICKPAY_PROFILE_ID`, `CLICKPAY_SERVER_KEY`) are optional until a ClickPay config is enabled. Gateway secrets at rest use `SECRETS_ENCRYPTION_KEY` (empty = derived from `JWT_SECRET`).

Local/dev (`APP_ENV=local`/`dev`/`development`) also seeds a **demo catalog**: Starter / Pro / Business plans plus three credit packs (not commercial pricing; bootstrap plan stays unpriced and is not listed for checkout). Insert missing rows with `python -m app.billing.seed`, by re-running `python -m app.identity.bootstrap`, or by creating a Workspace. Existing demo rows are never overwritten.

Never commit real `.env` files.

## How you open the UI

Two local host patterns work. Pick one and keep API CORS / Vite URL aligned with it.

### A. localhost (simplest)

1. Leave Compose defaults or point Vite at the API:

   ```bash
   # apps/workspace_web/.env
   VITE_API_URL=http://localhost:8000
   VITE_ROOT_DOMAIN=localhost
   VITE_APP_ENV=local
   ```

2. Ensure `.env` `CORS_ORIGINS` includes `http://localhost:5174`.
3. Open http://localhost:5174

Workspace context is sent as `X-Workspace-Id` (and `X-Workspace-Slug` only while `APP_ENV=local` / `VITE_APP_ENV=local`). The API never trusts the slug header in production.

### B. `*.geem.dm` (tenant-host DX)

Compose and `.env.example` assume this: API at `http://api.geem.dm:8000`, SPA at `http://app.geem.dm:5174` or `http://{slug}.geem.dm:5174`.

Point those names at `127.0.0.1`. Either:

**`/etc/hosts` (fixed names only):**

```text
127.0.0.1 api.geem.dm app.geem.dm geem.dm
```

Add one line per workspace slug you care about (`acme.geem.dm`, …).

**dnsmasq (wildcard `*.geem.dm`):**

```text
address=/geem.dm/127.0.0.1
```

Then open **http://app.geem.dm:5174**, not `http://api.geem.dm:5174` (that host is the API, not the SPA).

Vite already allows Host headers for `.geem.dm`. With `APP_ENV=local`, the API also allows CORS for `http(s)://{sub.}geem.dm[:port]` in addition to the exact `CORS_ORIGINS` list.

## Path 1 — full stack with Docker (recommended)

```bash
cp .env.example .env
# edit .env → OPENROUTER_API_KEY, optional BOOTSTRAP_ADMIN_*

cp apps/workspace_web/.env.example apps/workspace_web/.env
# if you use localhost instead of geem.dm, set VITE_API_URL=http://localhost:8000

cd infra
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| Workspace UI | http://localhost:5174 or http://app.geem.dm:5174 |
| Legacy MVP UI | http://localhost:5173 |
| API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |
| Live | http://localhost:8000/api/health/live |
| Ready | http://localhost:8000/api/health/ready |
| MinIO console | http://localhost:9101 (user `minio` / password from compose, default `change-me`) |

Compose starts Postgres, Redis, Qdrant, MinIO, runs `alembic upgrade head` on API boot, then Uvicorn (`--reload`) and a Celery worker (`concurrency=2`). API and workspace UI bind-mount source for live reload.

### First admin user

After the API is healthy:

```bash
cd infra
docker compose exec api python -m app.identity.bootstrap
```

Requires `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`. Safe to re-run: existing users are promoted to platform admin; password is unchanged unless you pass `--reset-password`.

This also ensures the default Workspace, the internal Platform Knowledge Workspace, the Geem General Expert, and (when `APP_ENV` is local/dev) the demo billing catalog.

Or register from the Workspace UI (`/api/auth/register`) and skip bootstrap. To seed only the demo plans/credit packs later:

```bash
docker compose exec api python -m app.billing.seed
```

### Logs and teardown

```bash
cd infra
docker compose ps
docker compose logs -f api worker workspace_web
docker compose down          # keep volumes
docker compose down -v       # wipe Postgres / Qdrant / MinIO / Redis data
```

## Path 2 — dependencies in Docker, API and UI on the host

Use this when you want a debugger, `pytest` against real services, or faster UI iteration without rebuilding images.

1. Start only data services:

   ```bash
   cd infra
   docker compose up -d postgres redis qdrant minio minio-init
   ```

2. Point **host** processes at published/localhost ports. Create `apps/api/.env` or export:

   ```bash
   DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag
   REDIS_URL=redis://localhost:6379/0
   QDRANT_URL=http://localhost:6333
   MINIO_ENDPOINT=localhost:9100
   ```

   Compose does **not** publish Postgres, Redis, or Qdrant to the host. Either add temporary `ports:` in a local override file, or keep using Path 1 for those services.

   MinIO **is** published: API `9100`, console `9101`. Host `MINIO_ENDPOINT` must be `localhost:9100` (not `minio:9000`).

3. API + worker (from `apps/api`):

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   alembic upgrade head
   python -m app.identity.bootstrap   # optional
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   In a second terminal:

   ```bash
   source .venv/bin/activate
   celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=2
   ```

4. Workspace UI:

   ```bash
   cd apps/workspace_web
   npm install
   npm run dev
   ```

## Path 3 — API unit tests only (no Docker)

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Generate PDF fixtures:

```bash
python tests/fixtures/generate_fixtures.py
```

Golden eval (needs ready documents + OpenRouter):

```bash
python -m app.eval.run
```

Workspace UI tests:

```bash
cd apps/workspace_web
npm install
npm test
npm run typecheck
```

## Workspace UI scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite on 5174 |
| `npm run build` | Typecheck + production `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run typecheck` | `tsc -b` |
| `npm run lint` | ESLint |
| `npm test` | Vitest |

API access from the UI goes through `src/services/api/` only. `VITE_*` values are baked in at **build** time (`npm run build`); `npm run dev` reads them on each start.

## Auth, cookies, CORS (local)

- Access token: in-memory `Authorization: Bearer`
- Refresh: HttpOnly cookie `geem_refresh`, `Path=/api/auth`, `SameSite=Lax`, `Secure=false` when `APP_ENV=local`
- Browser must call the API with `credentials: 'include'` (already done in the Workspace client)
- `CORS_ORIGINS` is an exact-origin list (no `*`)
- Do not put `http://api.geem.dm:5174` in `CORS_ORIGINS` — that is not an SPA origin

## What not to expect from the legacy stack

- `apps/web` still builds, but unauthenticated Document / Query / Jobs calls return **401** after the SaaS cutover. Do not turn `AUTH_REQUIRED` off to make it work.
- `scripts/smoke_test.sh` still posts to `/api/documents` without auth. It will fail against the current API.

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `/api/health/ready` is 503 | `docker compose ps`; `checks` in the JSON names postgres / redis / qdrant / minio |
| Login works, refresh fails | SPA origin vs API host; cookie is host-only on the **API** host; CORS must list the SPA origin |
| CORS errors on `*.geem.dm` | `APP_ENV=local` and `APP_ROOT_DOMAIN=geem.dm`; open `app.geem.dm:5174`, not `api.geem.dm:5174` |
| Upload stays `queued` | `worker` container is up; `docker compose logs -f worker` |
| OCR / chat failures | `OPENROUTER_API_KEY`, credits, and `checks.openrouter` on `/api/health/ready` |
| Embedding dimension errors | Do not mix embedding models in one Qdrant collection; change `QDRANT_COLLECTION` when switching models |
| `JWT_SECRET` startup error | Only raised when `APP_ENV` is not local/dev/test — keep `APP_ENV=local` on your laptop |
| Vite “blocked host” | `allowedHosts` already includes `.geem.dm`; confirm you are not using a different TLD without updating `vite.config.ts` |
