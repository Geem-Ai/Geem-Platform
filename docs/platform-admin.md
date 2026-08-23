# Platform Admin

Geem Platform Admin is a **separate security domain** from Workspace administration.

**Workspace Owner ≠ Platform Admin.**  
A Workspace Owner, Administrator, or custom role with every `WorkspacePermission` still cannot call `/api/platform/*` unless `users.platform_role == admin`.

`dashboard_web` is **not a tenant application**. It must not send `X-Workspace-Slug`, `X-Workspace-Id`, or treat Workspace membership as authorization.

## Surfaces

| Surface | App | Host (example) |
|---------|-----|----------------|
| Tenant Workspace | `apps/workspace_web` | `{slug}.geem.ai` / `hub.geem.ai` |
| Platform Admin | `apps/dashboard_web` | `APP_ADMIN_HOST` (production: `mtfm.geem.ai`) |
| Marketing | `apps/landpage_web` | `www.geem.ai` / `geem.ai` |

Do not hardcode `mtfm.geem.ai` in domain logic. Use `Settings.app_admin_host` (`APP_ADMIN_HOST`).

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
mtfm.geem.ai  →  dashboard_web (nginx; /api proxied to FastAPI)
               →  /api/platform/*  (Host = APP_ADMIN_HOST)
```

Login stays on Identity: `POST /api/auth/login` then `GET /api/platform/me`.

## Bootstrap API

`GET /api/platform/me` — session user + `platform_role` + `authorized`. No tenant Workspace is resolved.

## Phase 12B — Workspace & User administration

Authoritative inventory and lifecycle (disable/enable). Workspace RBAC never authorizes these routes.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/platform/workspaces` | Paginated; default `kind=tenant`; filters: search, status, kind, created_from/to |
| GET | `/api/platform/workspaces/{id}` | Detail + owners, subscription summary, resource counts |
| GET | `/api/platform/workspaces/{id}/members` | Dynamic `role_id` / role name (Phase 10 RBAC) |
| POST | `/api/platform/workspaces/{id}/disable` | Sets `status=suspended`; reason required; audited |
| POST | `/api/platform/workspaces/{id}/enable` | Restores `active`; audited |
| GET | `/api/platform/users` | Paginated; filters: search, status, platform_role |
| GET | `/api/platform/users/{id}` | Detail + tenant memberships |
| POST | `/api/platform/users/{id}/disable` | Sets `status=disabled`, revokes sessions; cannot self-disable |
| POST | `/api/platform/users/{id}/enable` | Restores `active` |

**Lifecycle:** Workspace disable ≠ soft-delete. Suspended Workspaces fail closed at `require_workspace`, API-key auth, Chat Widget public messages, and connector webhooks via `require_active_workspace`. System Workspaces (`kind=system`) cannot be disabled.

## Phase 12C — Plans, subscriptions & credits

Orchestrates existing Workspace Geem billing (`PlanService`, `SubscriptionService`, `CreditService`, `EntitlementService`). Does **not** administer App Store `app_plans` / gateways / purchases.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/platform/entitlement-catalog` | Canonical entitlement keys/units |
| GET | `/api/platform/plans` | Paginated; filters: search, status, currency |
| POST | `/api/platform/plans` | Create plan + entitlements atomically |
| GET | `/api/platform/plans/{id}` | Detail + subscriber count |
| PATCH | `/api/platform/plans/{id}` | Metadata/entitlements; reason required if in-use entitlements change |
| POST | `/api/platform/plans/{id}/activate` | `status=active` |
| POST | `/api/platform/plans/{id}/deactivate` | `status=archived`; bootstrap plan protected |
| GET | `/api/platform/workspaces/{id}/subscription` | Current subscription |
| GET | `/api/platform/workspaces/{id}/subscriptions` | History (canceled + active) |
| POST | `/api/platform/workspaces/{id}/subscription/assign` | Manual assign/change; tenant only |
| GET | `/api/platform/workspaces/{id}/entitlements` | Effective entitlements via `EntitlementService` |
| GET | `/api/platform/workspaces/{id}/usage` | Usage snapshot (AI/experts/storage/credits) |
| GET | `/api/platform/workspaces/{id}/credits` | Balance + recent ledger |
| GET | `/api/platform/workspaces/{id}/credits/history` | Paginated visible ledger kinds |
| POST | `/api/platform/workspaces/{id}/credits/grant` | Append-only GRANT; idempotent `request_id` |

System Workspaces cannot receive tenant subscriptions or credit grants (`system_workspace_not_billable`). Credit packs / payment gateway CRUD deferred.

## Phase 12D — Platform Experts & Platform Knowledge

Orchestrates existing `ExpertService` / `ExpertAccessService` (Phase 3A domain). No duplicate Platform Expert model.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/platform/experts` | Paginated `{ items, total, limit, offset }`; filters: search, status, visibility, knowledge_mode, availability_mode, published |
| POST | `/api/platform/experts` | Create RAG-backed Platform Expert (draft by default) |
| GET | `/api/platform/experts/{id}` | Full Admin DTO (instructions, rag_config, counts) |
| PATCH | `/api/platform/experts/{id}` | Update fields; `visibility` / `availability_mode` route through publish/unpublish and access/all semantics with correct audit |
| POST | `/api/platform/experts/{id}/publish` | Publish |
| POST | `/api/platform/experts/{id}/unpublish` | Unpublish |
| DELETE | `/api/platform/experts/{id}` | Soft-delete (Geem General blocked); audited |
| GET | `/api/platform/experts/{id}/workspace-grants` | Paginated grant list with workspace search |
| POST | `/api/platform/experts/{id}/workspace-grants` | Grant tenant Workspace (legacy alias: `…/grants`) |
| DELETE | `/api/platform/experts/{id}/workspace-grants/{workspace_id}` | Revoke grant |
| POST | `/api/platform/experts/{id}/access/all` | `all_workspaces=true` |
| DELETE | `/api/platform/experts/{id}/access/all` | `selected_workspaces` only |
| GET | `/api/platform/experts/{id}/knowledge` | Linked Platform Knowledge documents + ingestion progress |
| POST | `/api/platform/experts/{id}/knowledge` | Upload PDF/TXT/MD (legacy alias: `…/upload`) |
| POST | `/api/platform/experts/{id}/knowledge/{document_id}/reprocess` | Re-ingest via existing pipeline |
| DELETE | `/api/platform/experts/{id}/knowledge/{document_id}` | Unlink from Expert (shared docs preserved) |
| POST | `/api/platform/knowledge/documents` | Upload to Platform Knowledge pool (unlinkable) |

Geem General (`knowledge_mode=general`) is protected from unpublish, disable-all, delete, and knowledge mutation. Workspace-facing `/api/experts` DTOs remain redacted.

Existing `/api/platform/experts*` scaffolding from Phase 3A uses the same host + `require_platform_admin` dependencies.

## Later slices

12D–12G should orchestrate existing services (ExpertService, app catalog, gateways, analytics) from `app.platform_admin`. Do not duplicate those domains. Mutations must write `audit_logs` (see [audit.md](./audit.md)).

## Local `dashboard_web`

```bash
cd apps/dashboard_web
cp .env.example .env
npm install
npm run dev    # port 5175
```

Docker Compose service: `dashboard_web` on **5175**. Does not replace `web` (5173), `workspace_web` (5174), or `landpage_web` (4321).

UAT Cloudflare Tunnel: **https://admin-uat.geem.ai** (see [development.md](./development.md) § C). Overlay sets `VITE_API_URL=https://api-uat.geem.ai`. `CORS_ORIGINS` must include `https://admin-uat.geem.ai`. This is not a tenant host.
