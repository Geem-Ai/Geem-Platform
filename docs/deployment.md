# Deployment (aaPanel)

How to run **Geem** on a Linux VPS managed with [aaPanel](https://www.aapanel.com/). Local development is documented in [development.md](./development.md).

This stack is **not** a single PHP site. You need Docker for Postgres, Redis, Qdrant, MinIO, FastAPI, and Celery. aaPanel supplies Nginx, TLS, the firewall, and a place to host the Workspace static files.

`apps/dashboard_web` is not deployed yet. `apps/landpage_web` is a static marketing site — build it separately and serve `dist/` from Nginx (see § Marketing site below).

## What you are deploying

| Piece | How it runs on the VPS |
|-------|-------------------------|
| PostgreSQL, Redis, Qdrant, MinIO | Docker Compose (private network only) |
| FastAPI (`apps/api`) | Docker Compose, port **8000** on localhost |
| Celery worker | Same image as the API, same Compose project |
| Workspace UI (`apps/workspace_web`) | `npm run build` → Nginx document root (`dist/`) |
| TLS, HTTP, SPA fallback | aaPanel website + Nginx |

Optional OpenTelemetry export (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`) is documented in [observability.md](./observability.md). The normal Compose stack does **not** include a collector. Celery Beat remains a dedicated `beat` service.

Do **not** run the Compose `web` / `workspace_web` services in production. Those images start Vite **dev** servers with bind mounts. Serve a production `dist/` from Nginx instead.

## Recommended host layout

Use **one public hostname** and reverse-proxy `/api` to FastAPI (same origin). That matches the HttpOnly refresh cookie (`Path=/api/auth`, host-only, `SameSite=Lax`, `Secure=true`).

Example for product domain `geem.ai` (replace with yours):

| Host | Role |
|------|------|
| `app.example.com` | Workspace SPA + `/api` → FastAPI |
| `*.example.com` (optional) | Same SPA + same `/api` proxy, for `{workspace}.example.com` |

Keep Postgres, Redis, Qdrant, and MinIO **off** the public internet. Compose already leaves Postgres / Redis / Qdrant unpublished; do not add `ports:` for them, and do not publish MinIO `9000`/`9001` in production.

Split-host (`app.` vs `api.`) also works (same-site cookies across subdomains). List canonical SPA origins in `CORS_ORIGINS`. The API also allows `https://{one-label}.{APP_ROOT_DOMAIN}` (never `*`, never suffix matching). Local/dev additionally allows `http` and ports.

## Server requirements

- Fresh Linux VPS (Ubuntu 22.04/24.04 or Debian 12 recommended)
- 4+ GB RAM (8 GB more comfortable: Qdrant + OCR concurrency + Celery)
- Disk for Postgres + MinIO objects + Qdrant vectors
- A domain you control, DNS A record to the VPS
- OpenRouter API key

aaPanel installer (official, run as root):

```bash
URL=https://www.aapanel.com/script/install_7.0_en.sh && curl -ksSO "$URL" && bash install_7.0_en.sh aapanel
```

Use the current installer from [aapanel.com](https://www.aapanel.com/) if that URL has moved.

## 1. aaPanel plugins

In **App Store** install:

1. **Nginx** (website stack)
2. **Docker** / Docker Manager (Compose)
3. **Node.js** version manager (build the SPA — pick **22.x**)
4. Optional: **Fail2ban**, **Log Watcher**

You do **not** need aaPanel’s PostgreSQL, Redis, or Python Project Manager if you follow this Compose-based path.

Open **Security** and allow **80** and **443**. Do not expose 5432, 6379, 6333, 8000, 9000, or 9001 to the world.

## 2. Put the code on the server

SSH (aaPanel → Terminal, or your own client):

```bash
mkdir -p /www/wwwroot
cd /www/wwwroot
git clone <YOUR_REPO_URL> geem
cd geem
```

Or upload a release tarball into `/www/wwwroot/geem`. Keep this path as `GEEM_ROOT` below.

## 3. Backend environment

```bash
cd /www/wwwroot/geem
cp .env.example .env
chmod 600 .env
```

Edit `.env` (aaPanel File Manager or `nano`). Production values that **must** change:

```bash
APP_ENV=production
APP_NAME=Geem
APP_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com
AUTH_REQUIRED=true
LEGACY_MVP_WRITES_ENABLED=false
APP_ROOT_DOMAIN=example.com
APP_ADMIN_HOST=admin.example.com

# ≥32 random characters. The example secret is rejected when APP_ENV=production.
JWT_SECRET=

TRUST_PROXY_HEADERS=true

BOOTSTRAP_ADMIN_EMAIL=you@example.com
BOOTSTRAP_ADMIN_PASSWORD=

# Compose service names (keep these if you use the prod Compose file below)
DATABASE_URL=postgresql+psycopg://rag:CHANGE_DB_PASSWORD@postgres:5432/rag
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=
MINIO_BUCKET=rag-documents
MINIO_SECURE=false

OPENROUTER_API_KEY=

# Workspace AI token pool. billed = round(provider_tokens * family multiplier).
# OCR defaults to 3×; chat/embed/rerank/title default to 1×.
# Optional JSON: AI_TOKEN_MODEL_MULTIPLIERS={"openai/gpt-5.6-luna":3}
```

If you will serve tenant hosts (`https://acme.example.com`) **without** proxying `/api` on those hosts, set `APP_ROOT_DOMAIN=example.com` so `https://{slug}.example.com` is allowed. Keep canonical hosts (`https://hub.example.com`) in `CORS_ORIGINS` (comma-separated, exact, no `*`).

Generate secrets on the VPS:

```bash
openssl rand -hex 32    # JWT_SECRET
openssl rand -hex 24    # Postgres / MinIO passwords
```

## 4. Production Compose file

`infra/docker-compose.yml` is a **dev** file (bind mounts, `--reload`, Vite, published MinIO). On the server, save this as `infra/docker-compose.prod.yml` and adjust the Postgres/MinIO passwords to match `.env`.

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: CHANGE_DB_PASSWORD
      POSTGRES_DB: rag
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag -d rag"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:v1.13.2
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: CHANGE_MINIO_PASSWORD
    volumes:
      - minio_data:/data
    restart: unless-stopped

  minio-init:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_started
    entrypoint: >
      /bin/sh -c "
      sleep 3;
      mc alias set local http://minio:9000 minio CHANGE_MINIO_PASSWORD;
      mc mb -p local/rag-documents || true;
      mc anonymous set none local/rag-documents;
      exit 0;
      "

  api:
    build:
      context: ../apps/api
      dockerfile: Dockerfile
    env_file:
      - ../.env
    environment:
      DATABASE_URL: postgresql+psycopg://rag:CHANGE_DB_PASSWORD@postgres:5432/rag
      REDIS_URL: redis://redis:6379/0
      QDRANT_URL: http://qdrant:6333
      MINIO_ENDPOINT: minio:9000
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_started
      minio-init:
        condition: service_completed_successfully
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health/live"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 180s
    restart: unless-stopped

  worker:
    build:
      context: ../apps/api
      dockerfile: Dockerfile
    env_file:
      - ../.env
    environment:
      DATABASE_URL: postgresql+psycopg://rag:CHANGE_DB_PASSWORD@postgres:5432/rag
      REDIS_URL: redis://redis:6379/0
      QDRANT_URL: http://qdrant:6333
      MINIO_ENDPOINT: minio:9000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      api:
        condition: service_healthy
    command: celery -A app.worker.celery_app worker --loglevel=INFO --concurrency=2
    restart: unless-stopped

  beat:
    build:
      context: ../apps/api
      dockerfile: Dockerfile
    env_file:
      - ../.env
    environment:
      DATABASE_URL: postgresql+psycopg://rag:CHANGE_DB_PASSWORD@postgres:5432/rag
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      api:
        condition: service_healthy
    command: celery -A app.worker.celery_app beat --loglevel=INFO --schedule /tmp/celerybeat-schedule
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
  minio_data:
```

Binding API as `127.0.0.1:8000` lets Nginx on the host proxy to it without publishing FastAPI to the public NIC.

Start (from `infra/`):

```bash
cd /www/wwwroot/geem/infra
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -sS http://127.0.0.1:8000/api/health/ready
```

You can do the same from aaPanel **Docker** → Compose / project, as long as the project directory is `infra/` and the env file path `../.env` still resolves.

### Bootstrap the first admin

```bash
cd /www/wwwroot/geem/infra
docker compose -f docker-compose.prod.yml exec api python -m app.identity.bootstrap
```

Then remove `BOOTSTRAP_ADMIN_PASSWORD` from `.env` (or rotate it) so it is not sitting in plaintext after first boot. Re-running bootstrap without `--reset-password` will not overwrite an existing password.

## 5. Build the Workspace SPA

Vite inlines `VITE_*` at **build** time. Set them before `npm run build`.

```bash
cd /www/wwwroot/geem/apps/workspace_web
cp .env.example .env.production
```

`.env.production`:

```bash
VITE_API_URL=https://app.example.com
VITE_ROOT_DOMAIN=example.com
VITE_APP_ENV=production
```

`VITE_API_URL` must be the origin the **browser** calls (this hostname, because Nginx will proxy `/api`). An empty value falls back to `http://localhost:8000` and will break production.

Using the Node version you installed in aaPanel:

```bash
cd /www/wwwroot/geem/apps/workspace_web
npm ci
npm run build
```

Output: `apps/workspace_web/dist/`. Point the aaPanel site root at that folder (or copy `dist/` into `/www/wwwroot/geem-app`).

### Marketing site (`apps/landpage_web`)

Build the static Astro site separately (no API proxy required):

```bash
cd /www/wwwroot/geem/apps/landpage_web
cp .env.example .env   # set PUBLIC_WORKSPACE_URL / PUBLIC_SIGNUP_URL for production
npm ci
npm run build
npm run verify
```

Output: `apps/landpage_web/dist/`. Create a **separate** aaPanel site for `geem.ai` / `www.geem.ai` with that document root. Use static `try_files` (not SPA fallback). Redirect `/` → `/ar` (see `apps/landpage_web/nginx.conf`).

## 6. aaPanel website + reverse proxy

1. **Website** → **Add site**
   - Domain: `app.example.com`
   - Root: `/www/wwwroot/geem/apps/workspace_web/dist`
   - Do not create a MySQL database for this site
2. **SSL** → Let’s Encrypt → enable HTTPS → force HTTPS
3. **Reverse proxy** (or edit Nginx config) for the API

If the UI reverse-proxy helper only supports a full-site proxy, skip it and paste the config below into **Website** → **Conf**.

### Nginx site config (SPA + API + SSE)

Replace `app.example.com`. Keep `client_max_body_size` at least `MAX_UPLOAD_MB` (default 100). Chat uses SSE (`/api/conversations/.../messages/stream`, `/api/query/stream`) — disable proxy buffering and use a long read timeout.

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name app.example.com;
    root /www/wwwroot/geem/apps/workspace_web/dist;
    index index.html;

    # aaPanel will inject ssl_certificate / ssl_certificate_key here

    client_max_body_size 110m;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
        proxy_cache off;
        gzip off;
        add_header X-Accel-Buffering no;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /assets/ {
        expires 7d;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }
}
```

`try_files ... /index.html` is required — the Workspace app is a React Router SPA.

Reload Nginx from aaPanel or `nginx -t && nginx -s reload`.

### Optional tenant wildcard

1. DNS: `A` record `*.example.com` → VPS
2. Same Nginx `server_name app.example.com *.example.com;` (and the same certificate — Let’s Encrypt wildcard needs DNS-01; otherwise issue per-host certs)
3. Same `root` and `/api/` proxy so `{slug}.example.com` is same-origin with the API

Reserved labels (`www`, `api`, `admin`, `app`, …) are not treated as workspace slugs.

## 7. DNS

| Record | Name | Value |
|--------|------|--------|
| A | `app` | VPS IPv4 |
| A | `*` (optional) | VPS IPv4 |

Wait for DNS, then issue the certificate in aaPanel.

## 8. Verify

```bash
curl -sS https://app.example.com/api/health/live
curl -sS https://app.example.com/api/health/ready
```

Ready should be HTTP 200 with `"postgres":"ok"`, `"redis":"ok"`, `"qdrant":"ok"`, `"minio":"ok"`, and `"openrouter":"configured"`.

Open `https://app.example.com`, register or log in with the bootstrap admin, create a Workspace, upload a PDF, and send a chat message. If upload sits on `queued`, the worker container is down or Redis is unreachable (`docker compose -f docker-compose.prod.yml logs -f worker`).

## 9. Updates

```bash
cd /www/wwwroot/geem
git pull
cd infra
docker compose -f docker-compose.prod.yml up -d --build
# API container already runs: alembic upgrade head

cd ../apps/workspace_web
npm ci
npm run build
```

Nginx already points at `dist/`; rebuild in place is enough. If you copied `dist/` elsewhere, copy it again.

If a release includes a one-off maintenance command (see `apps/api/migrations/README.md`), run it with `docker compose -f docker-compose.prod.yml exec api python -m app.maintenance.<module>`.

## 10. Backups

Stop or freeze writes if you need a consistent snapshot. Minimum:

| Data | Volume / path |
|------|----------------|
| Postgres | Compose volume `postgres_data` (or `pg_dump`) |
| Qdrant | `qdrant_data` |
| MinIO objects | `minio_data` |
| Redis | `redis_data` (sessions / Celery; can rebuild if lost) |
| Secrets | `/www/wwwroot/geem/.env` — off-box |

Example dump:

```bash
cd /www/wwwroot/geem/infra
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U rag rag > /www/backup/geem-$(date +%F).sql
```

aaPanel **Cron** can run that plus a `tar` of the MinIO/Qdrant volumes.

## 11. Hardening checklist

- [ ] `APP_ENV=production`
- [ ] `JWT_SECRET` ≥ 32 chars, not the example value
- [ ] `CORS_ORIGINS` exact HTTPS origins, never `*`; `APP_ROOT_DOMAIN` for `{slug}` hosts
- [ ] `TRUST_PROXY_HEADERS=true` only because Nginx **overwrites** `X-Forwarded-For`
- [ ] API bound to `127.0.0.1:8000`, not `0.0.0.0:8000` on a public interface
- [ ] MinIO / Qdrant / Postgres / Redis unpublished
- [ ] `VITE_APP_ENV=production` so the SPA does not send `X-Workspace-Slug`
- [ ] HTTPS forced; refresh cookie is Secure when `APP_ENV` is not local
- [ ] `BOOTSTRAP_ADMIN_PASSWORD` removed after first bootstrap
- [ ] OpenRouter key not in git, git, or world-readable files

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| aaPanel site 502 | API container not listening on `127.0.0.1:8000`; `docker compose ps` / `logs api` |
| API exits on boot | Weak `JWT_SECRET` or `CORS_ORIGINS` contains `*` under `APP_ENV=production` |
| Ready 503 | One of postgres / redis / qdrant / minio; read `checks` in the JSON |
| Login OK, refresh 401 | SPA origin ≠ cookie host; `VITE_API_URL` still `localhost`; mixed HTTP/HTTPS |
| CORS error | Split-host deploy missing that SPA origin in `CORS_ORIGINS` |
| Chat stream hangs then dies | Nginx `proxy_read_timeout` too low or `proxy_buffering` still on |
| Upload 413 | `client_max_body_size` below `MAX_UPLOAD_MB` |
| Upload queued forever | Worker not running; Redis URL mismatch between api and worker |
| Blank page on `/login` refresh | Missing SPA `try_files` fallback to `index.html` |
| UI calls `localhost:8000` | Rebuilt without `VITE_API_URL=https://app.example.com` |

## Alternative: aaPanel-native Postgres/Redis

Possible but more moving parts: install PostgreSQL and Redis from the aaPanel App Store, then point `.env` `DATABASE_URL` / `REDIS_URL` at `host.docker.internal` or the docker-bridge gateway, and keep Qdrant + MinIO + API + worker in Compose. Prefer the all-Compose file above unless you already operate those aaPanel databases.
