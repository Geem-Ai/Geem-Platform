# Workspace invitations

Tokenized **email invitations** let an authorized member invite someone by email. Accepting the invite creates a `workspace_membership` row with the invitation’s **dynamic role** (`role_id`). Membership is **not** created until the invitee authenticates with the same email and calls `POST /api/invitations/accept`.

Phase 10A is the invitations backend. Phase 10B is the Workspace Members UI. Phase 10C replaced static `admin|member` invite roles with workspace role IDs. See [rbac.md](./rbac.md).

## Lifecycle

State is derived from timestamps (no status column):

| State | Rule |
|-------|------|
| `accepted` | `accepted_at` is set |
| `revoked` | `revoked_at` is set |
| `expired` | pending and `expires_at <= now` |
| `pending` | not accepted, not revoked, `expires_at > now` |

- **Create** stores a hash of a one-time token and emails an accept URL.
- **Resend** rotates the token and expiry immediately; the previous raw token fails.
- **Revoke** sets `revoked_at` (soft). The row is never deleted. Tokens fail closed.
- **Accept** (authenticated) checks the token, expiry, revocation, and that the caller's normalized email matches the invitation.

Expiry TTL is `WORKSPACE_INVITE_TTL_HOURS` (default **72**). Tests may pass a `Settings` instance with a different value.

If a non-finalized invitation has already expired, creating a new invite for the same email **rotates** that row (new token + expiry) instead of inserting a duplicate. Historical accepted/revoked rows are kept.

## Authorization

Invitation **management** (create/list/resend/revoke) requires `members.invite`. Members without that permission receive `insufficient_workspace_role`.

Create and resend also require the workspace `status` to be `active` (`workspace_access_denied` otherwise), matching API-key creation. List and revoke remain available so pending invites can be inspected or cancelled on a suspended workspace.

`POST /api/invitations/accept` is session-authenticated but **not** workspace-scoped — the caller is joining.

Invite roles are **assignable workspace roles** (`role_id`). The Owner role cannot be assigned by invitation. The server revalidates that the role exists in the invitation’s workspace and is not `is_owner_role`. Cross-workspace role IDs fail closed.

Inviting an email that already has an active membership returns `already_workspace_member` (409). Resend of a still-open invite for that address is the same 409. The pending list omits those rows (they reappear if the membership is removed). Invitations are not a role-update API.

## APIs

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/api/workspaces/{workspace_id}/invitations` | `{ "email", "role_id" }` |
| `GET` | `/api/workspaces/{workspace_id}/invitations` | Pending only (`items`, `total`, `limit`, `offset`) |
| `POST` | `/api/workspaces/{workspace_id}/invitations/{id}/resend` | Rotates token |
| `DELETE` | `/api/workspaces/{workspace_id}/invitations/{id}` | Revoke (idempotent if already revoked) |
| `POST` | `/api/invitations/accept` | `{ "token" }` — authenticated |

Responses never include `token_hash`, the raw token, or SMTP credentials.

Typed error codes: `invitation_already_exists`, `already_workspace_member`, `invalid_invitation`, `invitation_expired`, `invitation_revoked`, `invitation_email_mismatch`, `invitation_already_accepted`, `invitation_not_found`, `email_delivery_failed`, `workspace_access_denied`.

Acceptance is **idempotent** for the rightful email: a second accept of an already-accepted token returns the existing membership instead of a unique-constraint error.

## Email providers

`EMAIL_PROVIDER`:

| Value | When |
|-------|------|
| `console` | **Local/test only.** Logs the message, including the accept URL (raw token). Forbidden in non-local env (`assert_secure_settings` + factory). |
| `smtp` | Optional SMTP. Required in non-local together with `SMTP_HOST`, `SMTP_FROM_EMAIL`, and `SMTP_USE_TLS=true`. `SMTP_TLS_VERIFY=false` is allowed for self-signed SMTP hosts (logs a warning). |

Domain services depend on `EmailProvider`; they do not know console vs SMTP.

Invitation mail is **multipart** (plain text + HTML), bilingual EN/AR, and tells the invitee they must authenticate with the invited address. Copy lives in `app.workspaces.invitation_email`. User-controlled names are HTML-escaped. The accept URL remains in the text body as `Accept: {url}` for local logs and tests. The HTML header uses the hosted Geem avatar (`https://geem.ai/assets/geem-avatar.webp`); the footer (and plain-text body) link to `https://geem.ai` and `https://geem.ai/support`.

**Transaction decision:** the invitation row is flushed, email is sent, then the transaction commits. If delivery fails, the transaction rolls back so the caller does not receive a 201 for an invitation that was never sent. There is no outbox/job queue in 10A.

### Local console / obtaining a token

1. Set `APP_ENV=local` (or `test`) and `EMAIL_PROVIDER=console` (the default).
2. Create an invitation via the API.
3. Read the API process log: the console adapter prints `Accept: {workspace_web_url}/invitations/accept?token=...`.
4. Automated tests inject `RecordingEmailProvider` via the `get_email_provider` FastAPI override. Production HTTP DTOs never return the raw token.

### SMTP

```text
EMAIL_PROVIDER=smtp
SMTP_HOST=...
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=noreply@example.com
SMTP_FROM_NAME=Geem
SMTP_USE_TLS=true
SMTP_TLS_VERIFY=true
```

STARTTLS uses `ssl.create_default_context()` when `SMTP_TLS_VERIFY=true`. `SMTP_TLS_VERIFY=false` skips certificate checks (self-signed SMTP) and logs a warning; STARTTLS is still required outside local/test (`SMTP_USE_TLS=true`). Local/test may disable TLS for tools like Mailhog.

Passwords are `repr=False` / `exclude=True` on Settings and must not be logged.

Accept URLs use `WORKSPACE_WEB_URL` (`Settings.effective_workspace_web_url`):

```text
{WORKSPACE_WEB_URL}/invitations/accept?token={RAW_TOKEN}
```

## Security

- Tokens: `secrets.token_urlsafe(32)` (≥256 bits). Stored as HMAC-SHA256 with the invitation pepper (`INVITATION_TOKEN_HASH_PEPPER`, falling back to the API-key pepper). Comparison is constant-time.
- Raw tokens are not persisted, not logged by `security_log`, and not present on list/detail DTOs.
- At most one non-finalized invitation per `(workspace_id, normalized_email)` (PostgreSQL partial unique index) plus a transaction advisory lock.
- Tenant isolation: management APIs resolve the workspace through existing membership/authz. Cross-workspace invitation IDs return `invitation_not_found`.
- Email normalization uses `identity.security.normalize_email` (strip + lower).
- Last-owner membership rules are unchanged; invitations cannot create owner memberships.

## Workspace UI (Phase 10B / 10C)

- Members page: `/members` (existing nav) with Members and Roles tabs. Users with `members.invite` can invite using assignable role IDs (Owner is excluded). Users with only `members.view` see the roster without management controls.
- Accept route: `/invitations/accept?token=...` (outside the workspace shell). Logged-out invitees sign in or register with `location.state.from` pointing back to this path. After a successful accept the app switches to the joined workspace and replaces the token URL with `/` (HomeRedirect chooses chat, overview, or the first allowed page).
- The raw token is sent only to `POST /api/invitations/accept`. It is not stored in `localStorage`, not placed in React Query keys, and not shown in toasts.
