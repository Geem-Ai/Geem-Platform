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
| `apps/landpage_web` | Public marketing site (Astro, port **4321**) |
| `apps/dashboard_web` | Platform Admin placeholder — Phase 12 |
| `infra/docker-compose.yml` | Local full stack |
| `.env` | API / worker / shared backend env (copy from `.env.example`) |
| `apps/workspace_web/.env` | Vite env (copy from `apps/workspace_web/.env.example`) |
| `apps/landpage_web/.env` | Marketing public env (copy from `apps/landpage_web/.env.example`) |

## Environment files

From the repo root:

```bash
cp .env.example .env
cp apps/workspace_web/.env.example apps/workspace_web/.env
cp apps/landpage_web/.env.example apps/landpage_web/.env
```

Set at least:

- `OPENROUTER_API_KEY` in `.env`
- `JWT_SECRET` — the example value is fine **only** when `APP_ENV=local`. Non-local processes refuse weak secrets.
- `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` if you want a first login without using the public register endpoint

Keep `AUTH_REQUIRED=true` and `LEGACY_MVP_WRITES_ENABLED=false`. Document / Query / Jobs require a logged-in Workspace user.

Local billing checkout (Phase 6A/6B) needs **exactly one enabled** `payment_gateway_configs` row. Seed/bootstrap/workspace provision enable **ClickPay** when `CLICKPAY_PROFILE_ID` and `CLICKPAY_SERVER_KEY` are set (any `APP_ENV`, including production). Otherwise they seed **Noop** only in `APP_ENV=local`/`test`. After payment verification the API redirects browsers (`Accept: text/html`) to the Workspace SPA (`/billing/payment/success|failed|pending?purchase=…`). It prefers the checkout `Origin` when that origin is allowed, then `WORKSPACE_WEB_URL`. Empty `WORKSPACE_WEB_URL` falls back to `http://app.{APP_ROOT_DOMAIN}:5174` in local/test (or `http://localhost:5174` when the root domain is localhost); production must set the SPA origin explicitly. The SPA re-fetches the purchase; it does not trust provider query parameters. Gateway secrets at rest use `SECRETS_ENCRYPTION_KEY` (empty = derived from `JWT_SECRET`).

Google Drive knowledge connector (Phase 9D): set `GOOGLE_DRIVE_CLIENT_ID` and `GOOGLE_DRIVE_CLIENT_SECRET` to make the adapter available. Optional: `GOOGLE_DRIVE_REDIRECT_URI` (defaults to `{APP_URL}/api/connectors/oauth/google_drive/callback`), `GOOGLE_DRIVE_SCOPE_MODE` (`selected_files` or `readonly`), `GOOGLE_DRIVE_PICKER_API_KEY`, `GOOGLE_DRIVE_APP_ID`. Without client id/secret the adapter stays registered but `available=false`. Workspace SPA may set `VITE_GOOGLE_DRIVE_PICKER_API_KEY` / `VITE_GOOGLE_DRIVE_APP_ID` instead of relying on the picker-session echo. Full A–Z setup (Google Cloud Console, Picker, webhooks, Workspace UI): [apps/google-drive.md](./apps/google-drive.md).

Microsoft OneDrive knowledge connector (Phase 9E / 9E.1): set `MICROSOFT_ONEDRIVE_CLIENT_ID` and `MICROSOFT_ONEDRIVE_CLIENT_SECRET` to make the adapter available. Optional: `MICROSOFT_ONEDRIVE_REDIRECT_URI` (defaults to `{APP_URL}/api/connectors/oauth/microsoft_onedrive/callback`), `MICROSOFT_ONEDRIVE_TENANT` (`common` for work/school + personal File Picker; or `organizations` / `consumers` / tenant GUID), `MICROSOFT_ONEDRIVE_SUBSCRIPTION_MINUTES` (Graph webhook lifetime). Without client id/secret the adapter stays registered but `available=false`. Full A–Z setup (Entra app, Graph permissions, subscriptions, Workspace UI): [apps/microsoft-onedrive.md](./apps/microsoft-onedrive.md).

WhatsApp / OpenWA channel connector (Phase 9F): set `OPENWA_BASE_URL` (default `https://whatsapp-hub.dalseen.sa`) and `OPENWA_API_KEY` to make the adapter available. Optional: `OPENWA_TIMEOUT_SECONDS` (default 30). The API key is backend-only and must never be exposed to `workspace_web`. Without an API key the adapter stays registered but `available=false`. Catalog app slug `whatsapp` is published with monthly SAR plans (`line` 79 / `desk` 199 / `ops` 449). Full A–Z setup (session lifecycle, QR/pairing, webhooks, Expert binding): [apps/whatsapp-openwa.md](./apps/whatsapp-openwa.md).

Local/dev (`APP_ENV=local`/`dev`/`development`) also seeds a **demo catalog**: Starter / Pro / Business plans plus three credit packs (not commercial pricing; bootstrap plan stays unpriced and is not listed for checkout). Insert missing rows with `python -m app.billing.seed`, by re-running `python -m app.identity.bootstrap`, or by creating a Workspace. Existing demo rows are never overwritten.

Never commit real `.env` files.

## How you open the UI

Localhost and `*.geem.dm` work without a tunnel. Public HTTPS uses two Compose overlays on **different hosts** — do not run both overlays on the same machine.

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

Vite already allows Host headers for `.geem.dm` and `.geem.ai`. The API allows CORS for one-label hosts under `APP_ROOT_DOMAIN` in addition to the exact `CORS_ORIGINS` list (`http(s)` + optional port when `APP_ENV=local`; `https://{slug}.{root}` otherwise).

### C. Cloudflare Tunnel — two overlays (do not mix hosts)

| Overlay | Host | Compose files | Public names | App servers |
|---------|------|---------------|--------------|-------------|
| **Production** | production server | `docker-compose.yml` + `docker-compose.tunnel.yml` | `hub.geem.ai`, `api.geem.ai`, `geem.ai`, `*.geem.ai` | baked nginx (`Dockerfile.prod`) |
| **UAT / this Mac** | development machine | `docker-compose.yml` + `docker-compose.uat.yml` | `app-uat.geem.ai`, `api-uat.geem.ai`, `landpage-uat.geem.ai` | Vite / Astro / Uvicorn `--reload` |

Do **not** start `docker-compose.tunnel.yml` on the UAT Mac (it would steal production DNS). UAT does **not** route `*.geem.ai`; workspace context is `https://app-uat.geem.ai` plus `X-Workspace-Id` (and `X-Workspace-Slug` while `APP_ENV` is local/dev). Prefer Cloudflare Access in front of both.

Cloudflare Free HTTP request bodies cap at **100 MB** (matches `MAX_UPLOAD_MB`). Missing credentials make `cloudflared` exit. Never commit `credentials.json`, `credentials-uat.json`, or ad-hoc dumps under `infra/cloudflared/` (the tree gitignores `*.json` and `Untitled`). If a tunnel credential file was ever pushed, rotate that tunnel’s secret in the Cloudflare dashboard and replace the local JSON.

#### Production overlay (`geem-dalseen`)

Ingress: [`infra/cloudflared/config.yml`](../infra/cloudflared/config.yml). Credentials: `infra/cloudflared/credentials.json` (gitignored).

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create geem-dalseen
cp ~/.cloudflared/<TUNNEL-UUID>.json infra/cloudflared/credentials.json
cloudflared tunnel route dns geem-dalseen hub.geem.ai
cloudflared tunnel route dns geem-dalseen api.geem.ai
cloudflared tunnel route dns geem-dalseen geem.ai
cloudflared tunnel route dns geem-dalseen "*.geem.ai"
```

| Public hostname | Origin (Docker DNS) |
|-----------------|---------------------|
| `hub.geem.ai` | `http://workspace_web:80` (production nginx) |
| `api.geem.ai` | `http://api:8000` |
| `geem.ai` / `www.geem.ai` | `http://landpage_web:80` (production nginx) |
| `{slug}.geem.ai` | `http://workspace_web:80` (reserved labels stay on the rows above) |

`.env` `CORS_ORIGINS` must include `https://hub.geem.ai`. `APP_ROOT_DOMAIN=geem.ai` also allows `https://{slug}.geem.ai`. The overlay rebuilds `workspace_web` and `landpage_web` as production nginx images with `VITE_*` / `PUBLIC_*` baked in, and sets `APP_URL` / `WORKSPACE_WEB_URL` plus `TRUST_PROXY_HEADERS=true`.

```bash
cd infra
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --force-recreate api workspace_web landpage_web cloudflared
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml logs -f cloudflared
```

OpenAPI: https://api.geem.ai/docs

#### UAT overlay (`geem-uat`, this Mac)

Ingress: [`infra/cloudflared/config.uat.yml`](../infra/cloudflared/config.uat.yml). Credentials: `infra/cloudflared/credentials-uat.json` (gitignored). Bind-mounts stay; Compose `environment` overrides Vite/Astro URLs so HTTPS UAT is not mixed with `api.geem.dm`. HMR uses `VITE_TUNNEL_HOST` / `PUBLIC_TUNNEL_HOST` (`wss` on 443).

One-time create on this Mac:

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create geem-uat
cp ~/.cloudflared/<TUNNEL-UUID>.json infra/cloudflared/credentials-uat.json
cloudflared tunnel route dns geem-uat app-uat.geem.ai
cloudflared tunnel route dns geem-uat api-uat.geem.ai
cloudflared tunnel route dns geem-uat landpage-uat.geem.ai
```

Specific CNAMEs override production `*.geem.ai` for those three names only.

| Public hostname | Origin (Docker DNS) |
|-----------------|---------------------|
| `app-uat.geem.ai` | `http://workspace_web:5174` (Vite) |
| `api-uat.geem.ai` | `http://api:8000` |
| `landpage-uat.geem.ai` | `http://landpage_web:4321` (Astro `npm run dev`) |

`.env` `CORS_ORIGINS` must include `https://app-uat.geem.ai`. Do not set `APP_ROOT_DOMAIN=geem.ai` on UAT (that would allow production `{slug}.geem.ai` origins on the UAT API). Overlay sets `APP_URL=https://api-uat.geem.ai`, `WORKSPACE_WEB_URL=https://app-uat.geem.ai`, and `TRUST_PROXY_HEADERS=true`. Local ports `8000` / `5174` / `4321` stay published.

```bash
cd infra
docker compose -f docker-compose.yml -f docker-compose.uat.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.uat.yml logs -f cloudflared
```

| Public (UAT) | Local (still works) |
|--------------|---------------------|
| https://app-uat.geem.ai | http://app.geem.dm:5174 |
| https://api-uat.geem.ai | http://api.geem.dm:8000 |
| https://landpage-uat.geem.ai | http://localhost:4321 |

OpenAPI: https://api-uat.geem.ai/docs

### Start on boot

Compose services use `restart: unless-stopped`. To also run `docker compose … up -d` at boot (in case containers were removed):

**Production host** (`geem-stack`):

```bash
mkdir -p ~/.config/systemd/user
cp infra/systemd/geem-stack.user.service ~/.config/systemd/user/geem-stack.service
systemctl --user daemon-reload
systemctl --user enable --now geem-stack.service
```

Root alternative: `sudo install -m 644 infra/systemd/geem-stack.service /etc/systemd/system/geem-stack.service && sudo systemctl enable --now geem-stack`.

**UAT / this Mac** (`geem-uat`; edit `WorkingDirectory` in the unit if the repo is not `~/PlaygroundProjects/ArabicRag`):

```bash
mkdir -p ~/.config/systemd/user
cp infra/systemd/geem-uat.user.service ~/.config/systemd/user/geem-uat.service
systemctl --user daemon-reload
systemctl --user enable --now geem-uat.service
```

macOS does not use systemd user units; start the UAT overlay from `infra/` (or Docker Desktop). Do not enable `geem-stack` and `geem-uat` on the same host.

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

Requires `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` in `.env`. Safe to re-run: existing users are promoted to platform admin; password is unchanged unless you pass `--reset-password`. To apply current `BOOTSTRAP_*` plan limits onto the existing bootstrap plan (normal boot does not overwrite them):

```bash
docker compose exec api python -m app.identity.bootstrap --resync-bootstrap-plan
```

This also ensures the default Workspace, the internal Platform Knowledge Workspace, the Geem General Expert, and (when `APP_ENV` is local/dev) the demo billing catalog.

Or register from the Workspace UI (`/api/auth/register`) and skip bootstrap. To seed demo plans/credit packs and the local checkout gateway later:

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

Workspace invitations (Phase 10): see [invitations.md](./invitations.md). Dynamic roles and permission-aware navigation (Phase 10C): see [rbac.md](./rbac.md). Soft-delete retention / purge (Phase 11A): [data-retention.md](./data-retention.md). Audit log: [audit.md](./audit.md). Members UI is `/members` (Members + Roles tabs) plus `/invitations/accept?token=`. Local/test default is `EMAIL_PROVIDER=console` (logs invite and email-verification URLs, including the raw token). Production must use `EMAIL_PROVIDER=smtp`. Do not expect the API to return invitation or verification tokens. After register (local/production), the Workspace SPA shows `/check-email`; the console log includes `/verify-email?token=`. `APP_ENV=test` skips the gate unless `EMAIL_VERIFICATION_REQUIRED=true`.

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

### Chat composer attachments

Paperclip → Images / PDF / Text. Files upload to ephemeral `chat_attachments` (TTL via `CHAT_ATTACHMENT_TTL_HOURS`) and are forwarded to the chat model as multimodal parts on the next turn. They are **not** Expert knowledge (no OCR ingest / Qdrant). Cap: `CHAT_ATTACHMENT_MAX_MB` (default 20; optional `VITE_CHAT_ATTACHMENT_MAX_MB` for the SPA).

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
- `CORS_ORIGINS` is an exact-origin list (no `*`); `APP_ROOT_DOMAIN` also allows one-label tenant hosts
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
| Vite “blocked host” | `allowedHosts` includes `.geem.dm` and `.geem.ai`; confirm you are not using a different TLD without updating `vite.config.ts` |
| Tunnel 1033 / cloudflared exits | Production: `credentials.json` + `-f docker-compose.tunnel.yml`. UAT: `credentials-uat.json` + `-f docker-compose.uat.yml`. Origins: prod nginx `:80` vs UAT Vite `:5174` / Astro `:4321` |
| Tunnel CORS / login refresh fails | Production: `CORS_ORIGINS` includes `https://hub.geem.ai`; browser calls `https://api.geem.ai`. UAT: `https://app-uat.geem.ai` in `CORS_ORIGINS`; browser calls `https://api-uat.geem.ai`. Recreate `workspace_web` after switching overlays |
