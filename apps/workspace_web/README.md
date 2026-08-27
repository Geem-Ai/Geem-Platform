# Geem Workspace Web

Production Workspace SaaS UI for **Geem**. Dev server port **5174**.

## Development

```bash
cd apps/workspace_web
npm install
npm run dev
```

Open http://localhost:5174

API base URL: `VITE_API_URL` (default `http://localhost:8000`).

## Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Vite dev server (5174) |
| `npm run build` | Typecheck + production build |
| `npm run typecheck` | TypeScript project references check |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |
| `npm run preview` | Preview production build |

## Auth + cookies (Phase 1B)

- Access token: in-memory only (`Authorization: Bearer`)
- Refresh: HttpOnly cookie via `credentials: 'include'` on `/api/auth/*`
- API `CORS_ORIGINS` must include `http://localhost:5174` (exact origin, not `*`)
- Local: send `X-Workspace-Id` always when selected; `X-Workspace-Slug` only when `VITE_APP_ENV=local` / DEV
- Production: prefer Host-derived workspace; `X-Workspace-Id` is a hint only — backend verifies membership

## Tenant query keys

Workspace-owned React Query keys must include workspace id:

```ts
['workspace', workspaceId, 'members']
```

On workspace switch / logout, previous workspace queries are removed.

## Docker Compose

From `infra/`:

```bash
docker compose --env-file ../.env up workspace_web
```

Service `workspace_web` maps host **5174** → container 5174 (Vite dev). The Cloudflare Tunnel overlay builds `Dockerfile.prod` and serves nginx on port **80** (published as host **5174**).

## Notes

- Metronic sample is read-only; see `METRONIC_PORT.md` and root `AGENTS.md`.
- Do not import from `samples/` at runtime.
