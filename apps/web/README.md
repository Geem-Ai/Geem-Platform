# Legacy MVP web (`apps/web`)

Historical single-tenant MVP UI for Geem / ArabicRag.

## Status after Phase 2C SaaS cutover

- This app **remains in the repository** and should **continue to build**.
- It is **not** the production Workspace product (`apps/workspace_web` is).
- Unauthenticated Document / Query / Jobs flows against the API **no longer work** after cutover (`AUTH_REQUIRED` + Workspace-only Document APIs).
- Do **not** weaken SaaS authentication to keep this client functional.
- Treat as historical / local-dev reference only unless deliberately rewired to authenticated Workspace APIs (out of scope for Phase 2C).
