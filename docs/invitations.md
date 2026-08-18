# Workspace invitations

Tokenized **email invitations** let a workspace owner or admin invite someone by email. Accepting the invite creates a `workspace_membership` row. Membership is **not** created until the invitee authenticates with the same email and calls `POST /api/invitations/accept`.

Phase 10A is the invitations backend. Phase 10B is the Workspace Members UI: `/members` invite/pending/resend/revoke, `/invitations/accept?token=`, and the role matrix.

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

Workspace invitation **management** (`POST/GET` list, resend, revoke) requires `WorkspaceAction.MANAGE_MEMBERS` (owner/admin today). Members receive `insufficient_workspace_role`.

Create and resend also require the workspace `status` to be `active` (`workspace_access_denied` otherwise), matching API-key creation. List and revoke remain available so pending invites can be inspected or cancelled on a suspended workspace.

`POST /api/invitations/accept` is session-authenticated but **not** workspace-scoped — the caller is joining.

Invite roles are `admin` or `member` only. `owner` cannot be assigned by invitation.

Inviting an email that already has an active membership returns `already_workspace_member` (409). Resend of a still-open invite for that address is the same 409. The pending list omits those rows (they reappear if the membership is removed). Invitations are not a role-update API.

## APIs

| Method | Path | Notes |
|--------|------|--------|
| `POST` | `/api/workspaces/{workspace_id}/invitations` | `{ "email", "role" }` |
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
| `smtp` | Optional SMTP. Required in non-local together with `SMTP_HOST`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS=true`, and `SMTP_TLS_VERIFY=true`. |

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

STARTTLS uses `ssl.create_default_context()` so the SMTP server certificate is verified. `SMTP_TLS_VERIFY=false` is allowed in local/test only (self-signed hosts). Non-local boot (`assert_secure_settings`) and the SMTP adapter refuse `SMTP_USE_TLS=false` and `SMTP_TLS_VERIFY=false` so invitation tokens are neither sent in the clear nor exposed to a TLS man-in-the-middle. Local/test may disable TLS for tools like Mailhog.

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

## Workspace UI (Phase 10B)

- Members page: `/members` (existing nav). Owner/admin can invite (`admin` or `member` only), list pending invitations, resend, and revoke. Members can view the roster and role matrix only.
- Accept route: `/invitations/accept?token=...` (outside the workspace shell). Logged-out invitees sign in or register with `location.state.from` pointing back to this path. After a successful accept the app switches to the joined workspace and replaces the token URL with `/members`.
- The raw token is sent only to `POST /api/invitations/accept`. It is not stored in `localStorage`, not placed in React Query keys, and not shown in toasts.
