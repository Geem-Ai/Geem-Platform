# Geem Admin (`apps/dashboard_web`)

Independent Platform Admin SPA. **Not a tenant application.** Do not implement this inside `apps/workspace_web`.

**Workspace Owner ≠ Platform Admin.** Access requires `users.platform_role = admin` on the API. Workspace roles and membership never grant this surface.

## Commands

```bash
cd apps/dashboard_web
cp .env.example .env
npm install
npm run dev          # http://localhost:5175
npm run typecheck
npm test
npm run test:e2e     # Playwright smoke (builds preview on :4174)
```

Point `VITE_API_URL` at the FastAPI origin (same Identity login as Workspace). The client never sends `X-Workspace-Slug` or `X-Workspace-Id`.

## Local hosts

| URL | Notes |
|-----|--------|
| http://localhost:5175 | Simplest; API host check is relaxed when `APP_ENV=local` |
| http://admin.localhost:5175 | Matches default `APP_ADMIN_HOST=admin.localhost` |
| http://admin.geem.dm:5175 | If you already use `*.geem.dm` |
| https://admin-uat.geem.ai | UAT Cloudflare Tunnel (`docker-compose.uat.yml`) |

Ensure `.env` `CORS_ORIGINS` includes `http://localhost:5175` (and `https://admin-uat.geem.ai` for UAT). Production reverse-proxy should serve `APP_ADMIN_HOST` (e.g. `admin.geem.ai`) and route `/api/platform/*` to FastAPI with that Host.

See [docs/platform-admin.md](../../docs/platform-admin.md) for the security model.
