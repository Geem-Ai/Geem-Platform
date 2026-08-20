# Agent instructions — Geem

## Product

- Product name: **Geem**
- GitHub repo: [Mohamkh93/Geem](https://github.com/Mohamkh93/Geem)
- Workspace SaaS UI: `apps/workspace_web`
- Legacy MVP UI: `apps/web` (keep runnable; do not rename/delete)
- Future: `apps/dashboard_web` (Platform Admin — Phase 12)
- Marketing: `apps/landpage_web` (Astro static site; independent of Phase 11/12)

## UI Boundary Rule (mandatory)

[`samples/metronic_vite_9.5.0`](samples/metronic_vite_9.5.0) is a **read-only UI reference**.

Production code must:

- **never** import from `samples/`
- **never** depend on `samples/` at runtime
- **never** modify Metronic sample source under `samples/`
- selectively port only the **Metronic AI Concept** (`src/ai/**`) and shared components that concept actually requires

Do **not** port wholesale:

- CRM
- Mail
- Calendar
- Todo
- Real Estate
- Store Inventory
- other Metronic concept apps

Metronic upgrades are **manual selective ports** into `apps/workspace_web`. Document ports in `apps/workspace_web/METRONIC_PORT.md`.

## Frontend apps

| App | Role |
|-----|------|
| `apps/web` | Existing MVP — leave intact during transition |
| `apps/workspace_web` | Geem Workspace SaaS product UI |
| `apps/dashboard_web` | Platform Admin (future — README placeholder only) |
| `apps/landpage_web` | Geem public marketing site (Astro static) |

Reuse patterns from `apps/web` by **copying/adapting**, not runtime imports across apps.

## Backend foundations

- Package boundaries under `apps/api/app/` (`common`, `identity`, `workspaces`, …) — implement domains per phase
- `RequestContext` + middleware in `app.common`
- `AUTH_REQUIRED=true` for SaaS Document/Query/Jobs after Phase 2C cutover (login/register/refresh/forgot-password/reset-password/verify-email/resend-verification/health remain public)
- OpenAPI / product title: **Geem**
- Alembic notes: `apps/api/migrations/README.md`

## Branding

- Vendor Geem avatar at `apps/workspace_web/public/brand/geem-avatar.webp`
- Do not hotlink `geem.ai` for the avatar in production
- Geem avatar = assistant / brand mark only — not the authenticated user avatar

## Metronic sample availability

`samples/` is **gitignored** (large commercial UI kit). Keep a local copy at:

```text
samples/metronic_vite_9.5.0
```

Obtain from your Metronic license / internal artifact store. Never commit sample source into production apps; selectively port into `apps/workspace_web` and record ports in `METRONIC_PORT.md`.
