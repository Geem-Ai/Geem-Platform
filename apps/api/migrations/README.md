# Alembic hygiene (Geem / Phase 0–2C)

- Script location: `apps/api/migrations` (`alembic.ini` → `script_location = migrations`)
- URL always comes from `Settings.database_url` via `migrations/env.py` (not the placeholder in `alembic.ini`)
- Import all SQLAlchemy models through `app.db.models` so `Base.metadata` is complete before autogenerate
- Naming: `NNNN_short_snake_description.py` (e.g. `0001_initial.py`, `0002_users_workspaces.py`)
- Prefer additive migrations; avoid editing applied revisions
- Soft-delete columns use `deleted_at` timestamptz nullable (see `app.common.soft_delete.SoftDeleteMixin`)
- Tenant tables must include `workspace_id` (UUID, indexed) starting Phase 2+ (documents)
- Phase 1A: `0002_identity_workspaces.py` — users, workspaces, workspace_memberships, sessions
- Phase 2A: `0003_documents_workspace_scope.py` — `documents.workspace_id` (nullable), `byte_size`, `deleted_at`, dual hash uniqueness
- Phase 2B: no Alembic for MinIO/Qdrant — use `python -m app.maintenance.phase2b_backfill_workspace_storage`
- Phase 2C: `0004_docs_workspace_nn.py` — `workspace_id NOT NULL`, drop legacy sha256 unique; run `python -m app.maintenance.phase2c_migrate_legacy --apply` **before** this revision
- Phase 3A: `0005_experts_domain.py` — `workspaces.kind`, experts / expert_sources / expert_documents / workspace_expert_grants; Platform Knowledge system Workspace via bootstrap (not Alembic seed)
- Phase 3B: no Alembic for Qdrant `expert_ids` — payload index via `QdrantVectorStore._ensure_payload_indexes`; maintenance: `python -m app.maintenance.sync_expert_vector_memberships`, `python -m app.maintenance.phase3b_legacy_library`
- Phase 4A: `0006_conversations_messages.py` — `conversations` (consumer workspace + user + expert, soft-delete) + `messages` (role/content/citations/status, optional `usage_event_id`)
- Phase 4B: no Alembic — `ChatOrchestrator` + `POST .../messages/stream` + retry SSE; bounded chat history via settings; generation lock (Redis/memory)
- Phase 4D: `0007_geem_general_expert.py` — `experts.knowledge_mode` (`rag`|`general`) + unique platform general Expert; seed via `python -m app.identity.bootstrap` (`ensure_geem_general_expert`)
- Phase 4 polish: `0008_conversation_favorites.py` — `conversations.favorited_at` (mirrors pin)
- Phase 5A: `0009_plans_subscriptions_usage.py` — plans, plan_entitlements, subscriptions (one active per Workspace), credit_accounts, append-only credit_ledger_entries, usage_period_counters, storage_usage_events. Bootstrap/dev plan is seeded in application code (`PlanService.ensure_bootstrap_plan`), not SQL. Payment gateways are Phase 6.
- Phase 5B: `0010_ai_usage_reservations.py` — `ai_usage_reservations` (reserve/settle/release + request_id idempotency), `usage_events` Workspace/User/Expert/conversation/message attribution, CHECK `credit_accounts.balance >= 0` and grant `remaining_amount >= 0`. Token reservation is application-enforced with `SELECT … FOR UPDATE` + advisory locks. No payment gateways.
- Phase 5C: `0011_storage_expert_quota.py` — `workspace_resource_usage` (in-flight `reserved_bytes`) + `storage_reservations`. Expert allowance is live COUNT of active Workspace Experts (`type=workspace`, not deleted). Billable storage is live SUM of active `documents.byte_size`; logical delete releases it; restore re-checks quota. Physical MinIO/Qdrant purge remains a later lifecycle concern.
- Phase 6A: `0012_billing_gateways_purchases.py` — `plans.price_amount`/`currency`, `payment_gateway_configs` (encrypted credentials, at most one enabled), `credit_packs`, `purchases` (immutable payload, `cart_id`/`tran_ref` uniqueness, return token hash). Checkout is hosted-page redirect + server-side query; no webhooks. Local/dev demo plans + credit packs are seeded in application code (`app.billing.seed.ensure_local_demo_catalog`), not SQL.
- Phase 7A: `0013_api_keys.py` — `api_keys` (HMAC-SHA256 hashed secrets, scopes, persistent `revoked_at`) + nullable `usage_events.api_key_id`. Public `/api/v1/chat` is Phase 7B.
- Phase 7B: no Alembic — `POST /api/v1/chat` (API-key auth, entitlement key `api_requests_per_minute` seeded on bootstrap/demo plans, Redis rate limiter). Workspace Chat persistence is unchanged.

### Document tenancy (Phase 2C final)

| Population | `workspace_id` | Access path |
|------------|----------------|-------------|
| Workspace SaaS | UUID NOT NULL | Valid Bearer + workspace membership |
| Legacy MVP | removed | Unauthenticated Document/Query/Jobs → **401** |

**Invalid Bearer never falls back to any document population** (401).

### Phase 2C store layout

- MinIO canonical keys: `workspaces/{workspace_id}/documents/{document_id}/original.pdf`
- Legacy flat keys may remain as orphaned rollback copies until a later purge command
- Production Document reads do **not** dual-read flat keys
- Qdrant Workspace payload includes `workspace_id`; `search_workspace` always filters in Qdrant
- Celery: `ingest_document(document_id, mode, workspace_id, actor_id?)` with fail-closed ownership check
- HTTP RAG uses `WorkspaceRagScope` only

### AUTH_REQUIRED (Phase 2C)

| Route class | Behavior |
|-------------|----------|
| `/api/auth/login`, `/register`, `/refresh` | Public |
| `/api/auth/*` (authenticated) + `/api/workspaces/*` | Always authenticated |
| `/api/documents/*`, `/api/query*`, `/api/jobs/*`, `/api/experts/*`, `/api/conversations/*`, `/api/subscription`, `/api/entitlements`, `/api/usage/*`, `/api/billing/*` (except return), `/api/api-keys/*` | Authenticated Workspace required |
| `/api/v1/chat` | Workspace API key (`Authorization: Bearer geem_sk_…`, scope `chat:write`). Session cookies are ignored. |
| `/api/billing/return/{gateway}/{purchase_id}` | Opaque return token (`rt`); server-side gateway query. Not payment proof. |
| `/api/health/*` | Public |

Production / SaaS default: `AUTH_REQUIRED=true`, `LEGACY_MVP_WRITES_ENABLED=false`.

### Cookie / CORS topology (Phase 1C)

| Env | Frontend | API | Cookie | CORS |
|-----|----------|-----|--------|------|
| Local | `http://localhost:5174` (or configured host:5174) | `http://localhost:8000` | Host-only on API host, `Path=/api/auth`, `HttpOnly`, `SameSite=Lax`, `Secure=false` | Exact origins in `CORS_ORIGINS` + credentials |
| Production | `{workspace}.geem.ai` or `app.geem.ai` | `api.geem.ai` | Host-only on API host (not shared across customer domains), `Secure=true`, `SameSite=Lax` | Exact allowlist — never `*` |

**Custom domains (`chat.customer.com`):** current cookie is API-host-only. Cross-site custom domains would need a BFF/same-origin proxy or a deliberate cross-site cookie strategy later — do not treat Phase 1 cookies as portable to arbitrary customer origins.

**Subdomain SPA CORS:** prefer reverse-proxy same-origin (`geem.ai` → API + SPA) or an explicit allowlist derived from `APP_ROOT_DOMAIN` (never naive suffix matching).

**Refresh reuse grace:** `REFRESH_REUSE_GRACE_SECONDS` (default 60) allows multi-tab reuse of a just-rotated refresh token without wiping the session family. Delayed replay after grace still revokes all sessions.

Commands (from `apps/api`):

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe_change"
alembic downgrade -1
```

Phase 2C maintenance:

```bash
python -m app.maintenance.phase2c_migrate_legacy --dry-run
python -m app.maintenance.phase2c_migrate_legacy --apply
python -m app.maintenance.phase2c_migrate_legacy --verify
```
