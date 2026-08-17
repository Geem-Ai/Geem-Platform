# Google Drive app — configuration A–Z

End-to-end setup for Geem’s **Google Drive** knowledge connector (Phase 9D): Google Cloud project → OAuth → Picker → Geem env → Workspace install → Expert knowledge.

Without `GOOGLE_DRIVE_CLIENT_ID` and `GOOGLE_DRIVE_CLIENT_SECRET`, the adapter stays registered but `available=false` (`google_drive_not_configured`). Install/browse still work; Connect and OAuth do not.

---

## 1. What you get

| Capability | Behavior |
|------------|----------|
| App catalog | Free published app slug `google-drive`, connector key `google_drive` |
| Auth | OAuth 2.0 (authorization code + PKCE), offline refresh |
| Default scopes | OpenID + email + profile + **`drive.file`** (files the user picks / opens with the app) |
| Optional scopes | `drive.readonly` when `GOOGLE_DRIVE_SCOPE_MODE=readonly` |
| File pick | Google Picker in Workspace UI |
| Ingest | PDF, plain text, Markdown, Google Docs (exported as Markdown) |
| Sync | Incremental Drive changes + `changes.watch` webhooks; Celery Beat renews watches |

**Not supported (ingest):** Google Sheets, Google Slides, and other MIME types outside the list above.

---

## 2. Prerequisites

1. A Google account that can create a Cloud project (or use an existing org project).
2. Geem API + worker + Redis + Postgres running ([development.md](../development.md) or [deployment.md](../deployment.md)).
3. A **publicly reachable API base URL** for production/UAT webhooks (`APP_URL`). Local-only OAuth can work with `http://localhost` / `http://api.geem.dm:8000` redirect URIs; **push notifications require a URL Google can POST to** (e.g. Cloudflare Tunnel `https://api-uat.geem.ai`).
4. Workspace SPA origin allowed in `CORS_ORIGINS` (and matching `VITE_API_URL`).

---

## 3. Google Cloud Console — project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or select one). Note:
   - **Project ID** (string)
   - **Project number** — this is Geem’s `GOOGLE_DRIVE_APP_ID` / `VITE_GOOGLE_DRIVE_APP_ID` (Picker App ID).
3. Optionally set a display name under **APIs & Services → OAuth consent screen** branding.

---

## 4. Enable APIs

In the same project, enable:

| API | Why |
|-----|-----|
| [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com) | List/download/export files, changes feed, `changes.watch` |
| [Google Picker API](https://console.cloud.google.com/apis/library/picker.googleapis.com) | In-browser file picker |

Wait until both show as Enabled.

---

## 5. OAuth consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type:
   - **External** for most SaaS / local testing with personal Google accounts.
   - **Internal** only if every user is in your Google Workspace org.
3. Fill App name, User support email, Developer contact.
4. **Scopes** — add (or confirm Geem requests at runtime):
   - `openid`
   - `https://www.googleapis.com/auth/userinfo.email`
   - `https://www.googleapis.com/auth/userinfo.profile`
   - **Default (recommended):** `https://www.googleapis.com/auth/drive.file`
   - **Optional (broader):** `https://www.googleapis.com/auth/drive.readonly` — only if you set `GOOGLE_DRIVE_SCOPE_MODE=readonly`
5. **Test users** (while app is in Testing): add every Google account that will Connect Drive in Geem.
6. Publishing:
   - **Testing** is enough for internal/dev (100 test users).
   - **In production** for real tenants, submit for verification if Google requires it for sensitive scopes. Prefer `drive.file` to stay least-privilege.

---

## 6. Create OAuth client (Web application)

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Web application**.
3. Name: e.g. `Geem Google Drive`.
4. **Authorized JavaScript origins** (SPA hosts that load Picker / GSI):

   | Environment | Example origins |
   |-------------|-----------------|
   | Local `*.geem.dm` | `http://app.geem.dm:5174`, `http://geem.dm:5174` |
   | Localhost | `http://localhost:5174` |
   | UAT tunnel | `https://app-uat.geem.ai` |
   | Production | your Workspace SPA origin(s) |

5. **Authorized redirect URIs** — Google must call the **API** callback (not the SPA). Geem then **302-redirects the browser to the Workspace SPA** (`WORKSPACE_WEB_URL`):

   ```text
   Google → {APP_URL}/api/connectors/oauth/google_drive/callback
        → 302 → {WORKSPACE_WEB_URL}/apps/google-drive?oauth=success|error&…
   ```

   Register this exact URI with Google (must match `GOOGLE_DRIVE_REDIRECT_URI` / default):

   ```text
   {APP_URL}/api/connectors/oauth/google_drive/callback
   ```

   Examples:

   | `APP_URL` | Redirect URI (Google Cloud) |
   |-----------|------------------------------|
   | `http://api.geem.dm:8000` | `http://api.geem.dm:8000/api/connectors/oauth/google_drive/callback` |
   | `http://localhost:8000` | `http://localhost:8000/api/connectors/oauth/google_drive/callback` |
   | `https://api-uat.geem.ai` | `https://api-uat.geem.ai/api/connectors/oauth/google_drive/callback` |
   | `https://api.example.com` | `https://api.example.com/api/connectors/oauth/google_drive/callback` |

   Set `WORKSPACE_WEB_URL` to the SPA origin (e.g. `http://app.geem.dm:5174` or `https://app-uat.geem.ai`). Do **not** set it to `APP_URL` — the post-OAuth handoff must land on the frontend.

6. Create → copy **Client ID** and **Client secret**.

Never put the client secret in the SPA or Vite env. API only: `GOOGLE_DRIVE_CLIENT_SECRET`.

---

## 7. Picker API key (developer key)

1. **APIs & Services → Credentials → Create credentials → API key**.
2. Restrict the key:
   - **Application restrictions:** HTTP referrers — same SPA origins as above.
   - **API restrictions:** restrict to **Google Picker API** (and Drive API if Google requires it for your setup).
3. Copy the key → `GOOGLE_DRIVE_PICKER_API_KEY` and/or `VITE_GOOGLE_DRIVE_PICKER_API_KEY`.

The Picker also needs the **project number** as App ID (`GOOGLE_DRIVE_APP_ID` / `VITE_GOOGLE_DRIVE_APP_ID`).

You can supply Picker values on the **API** (echoed from `POST …/picker-session`) and/or on the **SPA** (`VITE_*`). SPA env wins when set in the frontend picker helper.

---

## 8. Geem API environment

Set in the root `.env` (Compose / host API). Template: [`.env.example`](../../.env.example).

```bash
# Required — makes connector available
GOOGLE_DRIVE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=...

# Optional — defaults to {APP_URL}/api/connectors/oauth/google_drive/callback
GOOGLE_DRIVE_REDIRECT_URI=

# selected_files → drive.file (default) | readonly → drive.readonly
GOOGLE_DRIVE_SCOPE_MODE=selected_files

# Optional — echoed on picker-session (or use VITE_* on SPA)
GOOGLE_DRIVE_PICKER_API_KEY=
GOOGLE_DRIVE_APP_ID=          # Google Cloud project number
```

Also ensure:

| Variable | Role for Drive |
|----------|----------------|
| `APP_URL` | OAuth default redirect base + webhook address Google calls (`…/api/connectors/webhooks/google_drive/{token}`) |
| `CORS_ORIGINS` | Must include Workspace SPA origin(s) |
| `WORKSPACE_WEB_URL` | Post-OAuth browser return to SPA (local often `http://app.geem.dm:5174`) |
| `SECRETS_ENCRYPTION_KEY` | Encrypts connection credentials at rest (empty in local derives from `JWT_SECRET`) |
| `REDIS_URL` | OAuth state (one-time) |

Restart **API** and **Celery worker** (and Beat) after changing these. Registration runs at process startup.

---

## 9. Workspace SPA environment

Optional Picker public values in [`apps/workspace_web/.env`](../../apps/workspace_web/.env.example):

```bash
# Public only — never put CLIENT_SECRET here
VITE_GOOGLE_DRIVE_PICKER_API_KEY=
VITE_GOOGLE_DRIVE_APP_ID=
```

Rebuild/restart `workspace_web` after changing `VITE_*`.

---

## 10. Scope mode choice

| `GOOGLE_DRIVE_SCOPE_MODE` | Drive scope | When to use |
|---------------------------|-------------|-------------|
| `selected_files` (default) | `drive.file` | Production default: only files opened/picked with the app |
| `readonly` | `drive.readonly` | Broader read access; harder verification / higher trust bar |

Changing mode after users already connected may require **reconnect** (reauthorization) so granted scopes match.

---

## 11. Webhooks & incremental sync

After connect/sync, Geem registers Drive `changes.watch` pointing at:

```text
{APP_URL}/api/connectors/webhooks/google_drive/{routing_token}
```

- Routing token ≠ connection UUID; stored encrypted.
- Channels expire (~1 day). Celery Beat task `renew_google_drive_watches` renews when expiration is within 24 hours.
- Google must reach `APP_URL` from the public internet. Pure localhost without a tunnel will still do **pull** sync when triggered, but **push** watches will fail or never fire.

For local UAT with public URLs, use the Cloudflare Tunnel overlay (`api-uat.geem.ai`) described in [development.md](../development.md).

---

## 12. Verify the adapter is available

1. Restart API with client id/secret set.
2. As a Workspace owner/admin, open Apps or call:

   ```http
   GET /api/apps/google-drive
   ```

   Expect connector metadata with the Drive key available (not `unavailable_reason: google_drive_not_configured`).
3. Install (if not already):

   ```http
   POST /api/apps/google-drive/install
   ```

---

## 13. In-product setup (Workspace UI)

1. Sign in to Geem Workspace (`http://app.geem.dm:5174` or your SPA URL).
2. Open **Apps** → **Google Drive** → **Install** (free catalog app).
3. **Connect** → browser redirects to Google → approve scopes → callback hits the API → redirect back to the SPA with success.
4. Status should show **Connected** (account email/name when Google returns profile).
5. Open an **Expert** → Knowledge → **Add Google Drive**:
   - App must be installed.
   - At least one active connection.
   - **Open Picker** → select supported files → Geem creates connector sources and enqueues ingest.

Credentials/tokens stay server-side; picker-session returns a **short-lived access token** only (never refresh token in the browser). The SPA keeps that token in memory only.

---

## 14. Supported file types

| Type | Ingest |
|------|--------|
| PDF (`application/pdf`) | Yes |
| Plain text | Yes |
| Markdown | Yes |
| Google Docs | Yes (export → Markdown) |
| Google Sheets / Slides | No |

Unsupported picks surface as a file-type error from the API.

---

## 15. Environment checklist

### Local (`*.geem.dm`)

```bash
# .env
APP_URL=http://api.geem.dm:8000
WORKSPACE_WEB_URL=http://app.geem.dm:5174
GOOGLE_DRIVE_CLIENT_ID=...
GOOGLE_DRIVE_CLIENT_SECRET=...
GOOGLE_DRIVE_SCOPE_MODE=selected_files
GOOGLE_DRIVE_PICKER_API_KEY=...
GOOGLE_DRIVE_APP_ID=...   # project number

# apps/workspace_web/.env (optional if API echoes picker fields)
VITE_API_URL=http://api.geem.dm:8000
VITE_GOOGLE_DRIVE_PICKER_API_KEY=...
VITE_GOOGLE_DRIVE_APP_ID=...
```

Google Cloud: redirect URI `http://api.geem.dm:8000/api/connectors/oauth/google_drive/callback`; JS origins include `http://app.geem.dm:5174`.

### UAT tunnel

```bash
APP_URL=https://api-uat.geem.ai
WORKSPACE_WEB_URL=https://app-uat.geem.ai
# same GOOGLE_DRIVE_* secrets
CORS_ORIGINS=...,https://app-uat.geem.ai
```

Google Cloud: HTTPS redirect + origins for `app-uat.geem.ai` / `api-uat.geem.ai`. Prefer this when testing watches.

### Production

- Strong `JWT_SECRET` / `SECRETS_ENCRYPTION_KEY` (not derived defaults).
- HTTPS `APP_URL` and redirect URI.
- Consent screen published/verified as required.
- Restricted API key referrers to production SPA hosts only.
- Celery worker **and** Beat running for ingest + watch renewal.

---

## 16. Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| App shows Drive but Connect fails / `google_drive_not_configured` | Missing `GOOGLE_DRIVE_CLIENT_ID` or `SECRET`; API not restarted |
| `redirect_uri_mismatch` | Console redirect URI ≠ `effective_google_drive_redirect_uri` (`GOOGLE_DRIVE_REDIRECT_URI` or `{APP_URL}/api/connectors/oauth/google_drive/callback`) |
| OAuth works, Picker blank / errors | Missing App ID (project **number**) or Picker API key; Picker API not enabled; referrer restrictions block SPA origin |
| “Access blocked” / app not verified | Consent screen Testing without your Google account as test user; or production verification pending |
| Reauth required after scope change | Mode flipped between `selected_files` and `readonly`; reconnect the connection |
| Files never update until manual sync | `APP_URL` not publicly reachable; webhook failing; Beat not running (`renew_google_drive_watches`) |
| Unsupported file type | Sheets/Slides or other MIME; only PDF/text/Markdown/Docs |
| CORS / cookie issues after OAuth return | SPA origin missing from `CORS_ORIGINS`; opened wrong host (e.g. `api.geem.dm:5174` instead of `app.geem.dm:5174`) |

---

## 17. Security notes

- Treat `GOOGLE_DRIVE_CLIENT_SECRET` like any production secret; never commit real `.env`.
- Prefer `selected_files` / `drive.file` unless you have a clear need for `drive.readonly`.
- Restrict OAuth client origins/redirects and API key referrers to known SPA/API hosts.
- Connection secrets are encrypted at rest; disconnect marks Expert connector sources unavailable.
- Do not log picker access tokens or refresh tokens.

---

## 18. Related docs & code

| Resource | Location |
|----------|----------|
| Local runbook | [docs/development.md](../development.md) |
| Deploy | [docs/deployment.md](../deployment.md) |
| Env templates | [`.env.example`](../../.env.example), [`apps/workspace_web/.env.example`](../../apps/workspace_web/.env.example) |
| Migrations note (9D) | [`apps/api/migrations/README.md`](../../apps/api/migrations/README.md) |
| Adapter | `apps/api/app/connectors/providers/google_drive/` |
| Picker UI | `apps/workspace_web/src/features/apps/google-drive/picker.ts` |
| Expert add-source dialog | `apps/workspace_web/src/features/experts/components/AddGoogleDriveKnowledgeDialog.tsx` |

OAuth callback path: `GET /api/connectors/oauth/google_drive/callback`  
Picker session: `POST /api/apps/google-drive/connections/{connection_id}/picker-session`  
Webhook: `POST /api/connectors/webhooks/google_drive/{routing_token}`
