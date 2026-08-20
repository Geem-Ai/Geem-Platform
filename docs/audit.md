# Audit logging (Phase 11A)

Geem records **security-sensitive mutations** in `audit_logs`. Ordinary reads
are not audited. Structured `geem.security` logs (`security_log`) remain for
operational tracing and are not a substitute for the table.

## Writer

`AuditService.record` / `record_audit` inserts a row and **flushes** in the
**same SQLAlchemy session** as the business mutation. Callers then `commit()`.

If a **required** audit flush fails, the writer uses a SAVEPOINT so the SQLAlchemy
session is not left in a failed state, then rolls back the outer transaction and
raises `AuditPersistenceError` (fail-closed). Optional events (`required=False`,
used by retention purge) roll back only the SAVEPOINT so the domain transaction
can continue.

Actor, workspace, and `request_id` default from `RequestContext` when omitted.

## Schema (conceptual)

| Field | Role |
|-------|------|
| `workspace_id` | Tenant scope (SET NULL if the Workspace row is later removed) |
| `actor_user_id` / `actor_api_key_id` | Who mutated |
| `action` | Stable name (`workspace.soft_deleted`, `api_key.created`, …) |
| `entity_type` / `entity_id` | Target |
| `request_id` | Correlation from `X-Request-Id` / middleware |
| `metadata` | Allowlisted JSON only |
| `created_at` | Server timestamp |

## Secret sanitization

`sanitize_audit_metadata`:

- Drops denylisted keys (passwords, JWTs, refresh tokens, invitation raw tokens,
  API key secrets, OAuth tokens, connector ciphertext, ClickPay server keys,
  cookies, authorization headers, full request bodies, …).
- Optionally keeps only an **allowlist** of keys (preferred at call sites).
- Truncates strings; never persists `password_hash` or plaintext secrets.

Tests in `tests/unit/test_audit_phase11a.py` assert blocked keys never land in
the JSONB column.

## Representative actions

AUTH / Workspace: password change/reset; workspace create/update/soft-delete/purge.

Members / RBAC: invite create/resend/revoke/accept; member role change/remove;
role create/update/permission change/delete.

Experts: create/update/soft-delete/purge.

API keys: create/revoke (plaintext secret is never stored or audited).

Billing: purchase paid/failed.

Apps: install/uninstall; purchase/renew fulfillment; connection created/disconnected/updated
(OpenWA channel settings); Chat Widget appearance/origin/expert updates.

Conversations: soft-delete/purge.

## Platform Admin (Phase 12+)

Platform Admin mutations are high-impact and **must** be audited when those APIs land (12B+). Each mutation records:

- `actor_user_id`
- `action`
- `entity_type` / `entity_id` (target)
- allowlisted metadata
- `request_id` when present
- `created_at`

`workspace_id` may be null for global platform actions. Do not authorize Platform Admin via Workspace RBAC. 12A does not write fake audit rows.

Purge outcomes use `required=False` so a tombstone Workspace can still be
anonymized if audit insert is degraded.
