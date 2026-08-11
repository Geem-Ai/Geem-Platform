# Geem Workspace Web

Production Workspace SaaS UI for **Geem**.

Legacy MVP remains at `apps/web` (port **5173**). This app runs on port **5174**.

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
| `npm run preview` | Preview production build |

## Docker Compose

From `infra/`:

```bash
docker compose up workspace_web
```

Service `workspace_web` maps host **5174** → container 5174. Existing `web` service is unchanged.

## Notes

- Metronic sample is read-only; see `METRONIC_PORT.md` and root `AGENTS.md`.
- Do not import from `samples/` or `apps/web` at runtime.
