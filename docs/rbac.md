# Workspace RBAC (Phase 10C)

Geem uses **workspace-scoped roles** and a **Geem-defined permission catalog**. Tenants assign permissions to roles; they cannot invent permission keys.

Frontend checks are UX only (sidebar, buttons, 403 page). Every protected API still enforces permissions on the server.

## Model

| Table | Purpose |
|-------|---------|
| `permissions` | Global catalog (`key` unique). Seeded from code. |
| `workspace_roles` | Roles that belong to one Workspace. |
| `workspace_role_permissions` | Role → permission assignments. |
| `workspace_memberships.role_id` | Member’s assigned role (`ON DELETE RESTRICT`). |
| `workspace_invitations.role_id` | Role granted on accept (not Owner). |

Constraints: unique `(workspace_id, name_normalized)` on roles; unique `(role_id, permission_id)` on assignments; unique `(workspace_id, user_id)` on memberships.

## Owner

The Owner role is **not** a normal custom role.

- `is_system` + `is_owner_role`
- Implicitly has every workspace permission (no stored assignment rows)
- Cannot be renamed, deleted, or have permissions edited
- Last-owner and ownership-transfer rules are unchanged
- Owner is the only role that can perform owner-only operations (`workspace.delete`, `members.promote_owner`)
- Owner cannot be used as an invitation role

This prevents a custom role from locking the workspace out.

## Default roles (migration)

Every Workspace is seeded with:

| `system_key` | Display name | Behavior |
|--------------|--------------|----------|
| `owner` | Owner | Protected full access |
| `admin` | Administrator | System default; rename/delete protected; permissions editable |
| `member` | Member | System default; rename/delete protected; permissions editable |

Migration `0024_workspace_rbac` creates tables, seeds the catalog, creates those three roles per workspace, backfills `role_id` from the legacy `owner|admin|member` column, then drops the string column after NOT NULL is enforced.

Existing members keep **equivalent** access: Member and Administrator permission sets match pre-10C `WorkspacePolicy` plus the routers that previously only required membership (billing view/manage/credits, API usage view, document CRUD). Access is not silently broadened or reduced.

Pending invitations map `admin`/`member` to the workspace’s default role IDs.

## Permission registry

Source of truth: `apps/api/app/workspaces/permissions.py` (`WorkspacePermission`). Frontend keys live in `apps/workspace_web/src/features/authz/permissions.ts` and **must stay aligned**.

Display copy is i18n: `permissions.{key}.name` / `.description` and `permissions.groups.{group}`.

### Inventory (endpoint → permission)

| Area | Permission | Typical use |
|------|------------|-------------|
| Overview | `workspace.view` | Overview + usage summary/entitlements |
| Workspace delete | `workspace.delete` | Owner only |
| Settings | `workspace_settings.view` / `.manage` | Settings page / mutations |
| Chat | `chat.use` | Conversations |
| Experts | `experts.view` / `.use` / `.create` / `.update` / `.delete` / `.manage_knowledge` | List, chat-with-expert, CRUD, knowledge |
| Storage | `storage.view` / `.download` / `.upload` / `.update` / `.delete` / `.reprocess` | File inventory |
| Apps | `apps.view` / `.manage` / `.connect` | Catalog, install/purchase, connectors |
| Members | `members.view` / `.invite` / `.update_role` / `.remove` / `.promote_owner` | List, invitations, role assignment |
| Roles | `roles.view` / `roles.manage` | Role catalog UI / mutations |
| API keys | `api_keys.view` / `.create` / `.revoke` | Key management |
| API usage | `api_usage.view` | API usage pages |
| Billing | `billing.view` / `.manage` / `.purchase_credits` | Read vs subscription vs credit packs |

`workspace.view` is granted to every **default** membership so Overview is not empty after migrate. Custom roles must include it explicitly if Overview should appear.

Chat uses `chat.use` only (it does not also require `storage.view`).

## Authorization service

`PermissionService` / `rbac_service.py`:

- `get_effective_permissions(membership)` — Owner → all keys; otherwise role assignments
- `has_permission` / `require_permission`
- `require_workspace_permission(context, key)` on routes

`RequestContext.effective_permissions` is loaded per request from the database. There is no long-lived permission cache; role edits apply on the next request. Frontend React Query is workspace-scoped (`['workspace', workspaceId, 'roles']`, etc.) and role updates invalidate `me` plus role queries.

Do not authorize with `membership.role == "admin"`.

## APIs

Workspace-scoped (session auth):

- `GET /api/workspaces/{id}/permissions` — catalog
- `GET /api/workspaces/{id}/roles`
- `GET /api/workspaces/{id}/roles/assignable` — excludes Owner
- `POST /api/workspaces/{id}/roles`
- `GET/PATCH/DELETE /api/workspaces/{id}/roles/{role_id}`

Delete returns `409 role_in_use` if members or pending invitations still reference the role. Unknown keys → `422 unknown_permission`. Cross-workspace role IDs fail closed.

Current-user effective permissions are on `/api/auth/me` and workspace DTOs: `role: {id,name,is_system,is_owner_role,system_key}` plus `permissions: string[]`.

Membership PATCH body is `{ "role_id": "..." }`. Invitation create body is `{ "email", "role_id" }`. Accept revalidates that the role exists, belongs to that workspace, and is not Owner.

## Frontend

- `usePermissions()` → `can` / `canAny` / `canAll` (from workspace DTO, not role names)
- Sidebar: `nav-config.ts` + `filterNavByPermissions` (hide empty parents)
- Route guards: `RequirePermission` → localized `ForbiddenPage` (no redirect to `/` for unauthorized pages)
- `/` (`HomeRedirect`): `chat.use` → `/chat`, else `workspace.view` → `/overview`, else first allowed nav, else 403
- Members page tabs: Members | Roles
- Invite/change-role selectors load assignable roles by ID

## How to add a permission

1. Add the key to `WorkspacePermission` and `PERMISSION_CATALOG` in `apps/api/app/workspaces/permissions.py`
2. Seed runs on API boot / workspace create (`seed_permission_catalog`); existing workspaces pick up new keys on next seed
3. Assign the key to default roles only if equivalent historical access requires it (`MEMBER_PERMISSION_KEYS` / `ADMIN_PERMISSION_KEYS`)
4. Call `require_workspace_permission` (or policy helpers) on the new endpoint
5. Add the same key to `apps/workspace_web/src/features/authz/permissions.ts`
6. Add EN/AR `permissions.{key}.name` and `.description`
7. Bind sidebar / `RequirePermission` / action buttons as needed
8. Add backend least-privilege tests and a frontend/nav test if the item is navigable

## Out of scope

No ABAC, document ACLs, permission DSLs, deny rules, org hierarchy, SSO/SCIM, or Platform Admin RBAC. Phase 11 Hardening is separate.
