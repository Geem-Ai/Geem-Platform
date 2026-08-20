# Platform Admin

Geem Platform Admin is a **separate security domain** from Workspace administration.

**Workspace Owner ≠ Platform Admin.**  
A Workspace Owner, Administrator, or custom role with every `WorkspacePermission` still cannot call `/api/platform/*` unless `users.platform_role == admin`.

`dashboard_web` is **not a tenant application**. It must not send `X-Workspace-Slug`, `X-Workspace-Id`, or treat Workspace membership as authorization.

## Surfaces

| Surface | App | Host (example) |
|---------|-----|----------------|
| Tenant Workspace | `apps/workspace_web` | `{slug}.geem.ai` / `hub.geem.ai` |
| Platform Admin | `apps/dashboard_web` | `APP_ADMIN_HOST` (example production value: `admin.geem.ai`) |
| Marketing | `apps/landpage_web` | `www.geem.ai` / `geem.ai` |

Do not hardcode `admin.geem.ai` in domain logic. Use `Settings.app_admin_host` (`APP_ADMIN_HOST`).

## Authorization

Canonical backend dependency: `require_platform_admin` in `apps/api/app/platform_admin/dependencies.py`.

It requires, fail-closed:

1. Authenticated **human session** (`get_current_user` — JWT + session row)
2. Active, non-deleted user (Identity policy)
3. `platform_role == admin`

| Caller | Result |
|--------|--------|
| Unauthenticated | 401 |
| Authenticated user with `platform_role=none` | 403 `platform_admin_required` |
| Workspace Owner / Administrator without platform_role | 403 |
| Workspace API key (`geem_sk_…`) | 401 (not a session JWT) |
| Platform Admin, including with zero Workspace memberships | allowed |

Do **not** authorize with Workspace membership, workspace roles, `WorkspacePermission`, `X-Workspace-*`, or API-key scopes.

Frontend `RequirePlatformAdmin` is UX only. `/api/platform/*` remains authoritative.

## Host boundary

`require_platform_admin_host` enforces `APP_ADMIN_HOST` in non-local environments.

- **Host is authoritative.** Reverse proxies must rewrite origin Host (Cloudflare Tunnel: `originRequest.httpHostHeader`).
- `X-Forwarded-Host` is never preferred over Host (clients can forge it even when `TRUST_PROXY_HEADERS=true`). It is only a last-resort fallback when Host is absent and trusted-proxy mode is on.
- Production: Host must match `APP_ADMIN_HOST`. Tenant hosts fail closed (`platform_admin_host_required`, 403).
- Local/test (`APP_ENV` local/dev/test): enforcement is relaxed so `dashboard_web` can call `http://localhost:8000` without a reverse-proxy Host rewrite.

Intended production layout:

```text
admin.geem.ai  →  dashboard_web
               →  /api/platform/*  (FastAPI, Host = APP_ADMIN_HOST)
```

Login stays on Identity: `POST /api/auth/login` then `GET /api/platform/me`.

## Bootstrap API

`GET /api/platform/me` — session user + `platform_role` + `authorized`. No tenant Workspace is resolved.

Existing `/api/platform/experts*` scaffolding from Phase 3A now uses the same host + `require_platform_admin` dependencies.

## Later slices

12B–12G should orchestrate existing services (`WorkspaceService`, billing/credits/usage, `ExpertService`, app catalog) from `app.platform_admin`. Do not duplicate those domains. Mutations must write `audit_logs` (see [audit.md](./audit.md)).

## Local `dashboard_web`

```bash
cd apps/dashboard_web
cp .env.example .env
npm install
npm run dev    # port 5175
```

Docker Compose service: `dashboard_web` on **5175**. Does not replace `web` (5173), `workspace_web` (5174), or `landpage_web` (4321).

UAT Cloudflare Tunnel: **https://admin-uat.geem.ai** (see [development.md](./development.md) § C). Overlay sets `VITE_API_URL=https://api-uat.geem.ai`. `CORS_ORIGINS` must include `https://admin-uat.geem.ai`. This is not a tenant host.
