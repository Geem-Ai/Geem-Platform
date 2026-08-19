# Data retention and purge (Phase 11A)

Geem uses **soft delete** for tenant-facing Workspace, Expert, and Conversation
deletion, then **retention purge** for permanent operational cleanup.

Document Storage (MinIO + Qdrant + derived RAG rows) remains the Phase 8
`DocumentService` path. Phase 11A does not add a second document deletion stack.

## Soft delete vs purge

| Stage | What happens |
|-------|----------------|
| Tenant DELETE | Sets `deleted_at`. Workspace also sets `status=archived`. Normal APIs stop resolving the row. |
| Retention window | Default **30 days** (`SOFT_DELETE_RETENTION_DAYS`). Rows stay for recovery/ops, not for product use. |
| Purge | Celery tasks hard-delete operational graphs or (Workspace) anonymize a tombstone. |

Restore is **not** exposed in Workspace UI. Expert restore still exists as a
backend path from Phase 3 and is unchanged.

## Configuration

| Setting | Default | Meaning |
|---------|---------|---------|
| `SOFT_DELETE_RETENTION_DAYS` | `30` | Age of `deleted_at` before purge is eligible |
| `PURGE_BATCH_SIZE` | `50` | Max entities per sweep invocation |

## Entities covered

- **Conversation** — messages hard-deleted; channel/widget bindings removed.
- **Expert** (workspace type only) — links, sources, grants, conversations for that Expert. **Documents are not deleted** merely because an Expert is purged (they may be shared). Qdrant `expert_ids` is reconciled through `ExpertVectorMembershipSynchronizer`.
- **Workspace** — most destructive. See below.

Users remain globally soft-deletable (`users.deleted_at`) from identity; that is
not this slice.

## Workspace purge semantics

On **soft delete** (`DELETE /api/workspaces/{id}`, permission `workspace.delete`,
owner-only in the default catalog):

- Workspace is no longer listed or resolvable (`deleted_at` + archived).
- API keys are revoked immediately (auth also fails because the Workspace is gone from `WorkspaceRepository.get_by_id`).
- Connector secrets are cleared (`ConnectorCredentialService.clear_all_secrets`) and connections marked `revoked`.
- Widget instances are disabled; App installation `config_encrypted` is wiped.
- Pending invitations are revoked.
- Workspace Experts and Conversations are soft-deleted.

On **purge** (after retention), `RetentionPurgeService.purge_workspace`:

1. Re-revoke access and destroy remaining connector rows (via `ConnectorRepository.purge_connection`).
2. Delete chat-attachment blobs (MinIO) and widget instances.
3. Purge conversations, then workspace Experts (bounded batches).
4. Purge Documents through **Phase 8** `DocumentService.purge_document_lifecycle` (MinIO + Qdrant, then hard-delete the PG row).
5. Cancel the Workspace subscription and App commercial access; wipe installation config.
6. Delete memberships, invitations, and workspace roles.
7. **Keep a tombstone Workspace row** (`purged_at` set, slug `deleted-{id prefix}`, name anonymized).

Purge jobs **never** take a user-supplied workspace id as authority. Sweep
queries select `kind=tenant AND deleted_at <= cutoff AND purged_at IS NULL`.
A missing or already-purged row is success (idempotent). If conversations,
workspace Experts, or documents remain after a pass, `purged_at` is **not**
set and the next invocation retries.

## `messages.usage_event_id`

This UUID is a **logical** pointer to `usage_events.id`, not a foreign key
(partitioned PK is `(id, created_at)`). Raw events are kept ~13 months. After
a partition drop, conversation/message APIs still succeed; the telemetry row
is simply gone. Do not reintroduce an `id`-only FK.

These keep `workspace_id` pointing at the tombstone so ledgers stay attributable:

- `purchases` (immutable checkout/fulfillment)
- `credit_accounts` / `credit_ledger_entries`
- `usage_events` / `usage_period_counters` / `storage_usage_events`
- `subscriptions` (canceled, not dropped)
- `app_licenses` / `app_subscriptions` / `app_installations` (revoked/uninstalled; secrets wiped)
- `audit_logs`

In-flight operational rows (`ai_usage_reservations`, `storage_reservations`,
connector sync/webhook/item rows, chat attachments) are removed.

## External cleanup retries

Postgres changes for one entity are committed together. MinIO and Qdrant are
**not** in that transaction. `DocumentService.purge_document_lifecycle` keeps the
Postgres document row when object or vector delete fails so the next purge can
retry. A failure in tenant A does not abort tenant B (per-entity try/except in
the sweep).

## Invoke purge

Celery Beat (UTC) runs the same Phase 11A tasks (idempotent, `SOFT_DELETE_RETENTION_DAYS`):

| Time | Task |
|------|------|
| 01:00 | `purge_deleted_conversations` |
| 01:15 | `purge_deleted_experts` |
| 01:30 | `purge_deleted_workspaces` |

Usage partition jobs stay at 00:10 / 00:20 / 00:30. See [usage-scaling.md](./usage-scaling.md)
and [observability.md](./observability.md).

Manual invoke with a worker:

```bash
cd apps/api
celery -A app.worker.celery_app call purge_deleted_conversations
celery -A app.worker.celery_app call purge_deleted_experts
celery -A app.worker.celery_app call purge_deleted_workspaces
```

Or in-process (tests / shell):

```python
from app.retention.service import RetentionPurgeService
RetentionPurgeService(db).purge_deleted_conversations()
```
