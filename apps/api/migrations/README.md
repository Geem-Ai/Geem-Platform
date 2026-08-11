# Alembic hygiene (Geem / Phase 0)

- Script location: `apps/api/migrations` (`alembic.ini` → `script_location = migrations`)
- URL always comes from `Settings.database_url` via `migrations/env.py` (not the placeholder in `alembic.ini`)
- Import all SQLAlchemy models through `app.db.models` so `Base.metadata` is complete before autogenerate
- Naming: `NNNN_short_snake_description.py` (e.g. `0001_initial.py`, `0002_users_workspaces.py`)
- Prefer additive migrations; avoid editing applied revisions
- Soft-delete columns use `deleted_at` timestamptz nullable (see `app.common.soft_delete.SoftDeleteMixin`)
- Tenant tables must include `workspace_id` (UUID, indexed) starting Phase 1+

Commands (from `apps/api`):

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe_change"
alembic downgrade -1
```
