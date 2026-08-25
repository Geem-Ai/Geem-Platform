# Docs

| Guide | When to use it |
|-------|----------------|
| [development.md](./development.md) | Run Geem locally (Docker Compose, host API, tests) |
| [deployment.md](./deployment.md) | Deploy on a VPS with aaPanel (Nginx + production Compose) |
| [architecture.md](./architecture.md) | Request paths, provider boundaries, pipeline versions |
| [integrations/client-agent-api.md](./integrations/client-agent-api.md) | Integrate Laravel AI or an OpenAI-compatible client with the paid Agents AI API |
| [apps/google-drive.md](./apps/google-drive.md) | Configure the Google Drive knowledge app (Google Cloud → OAuth → Geem → Expert) |
| [apps/microsoft-onedrive.md](./apps/microsoft-onedrive.md) | Configure the Microsoft OneDrive knowledge app (Entra → Graph → Geem → Expert) |
| [invitations.md](./invitations.md) | Workspace email invitations (tokens, providers, accept contract) |
| [rbac.md](./rbac.md) | Dynamic workspace roles, permission catalog, and permission-aware UI |
| [platform-admin.md](./platform-admin.md) | Platform Admin vs Workspace RBAC, APP_ADMIN_HOST, dashboard_web |
| [observability.md](./observability.md) | Optional OpenTelemetry, request IDs, safe attributes |
| [load-testing.md](./load-testing.md) | Isolation and quota concurrency harness commands |

API migration notes live in [`apps/api/migrations/README.md`](../apps/api/migrations/README.md).
