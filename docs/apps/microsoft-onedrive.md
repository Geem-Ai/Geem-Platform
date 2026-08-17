# Microsoft OneDrive app — configuration A–Z

End-to-end setup for Geem’s **Microsoft OneDrive** knowledge connector (Phase 9E / **9E.1**): Entra app registration → Graph OAuth → File Picker v8 (work/school **and** personal) → Geem env → Workspace install → Expert knowledge.

Without `MICROSOFT_ONEDRIVE_CLIENT_ID` and `MICROSOFT_ONEDRIVE_CLIENT_SECRET`, the adapter stays registered but `available=false` (`microsoft_onedrive_not_configured`). Install/browse still work; Connect and OAuth do not.

**9E scope:** Work/school OneDrive + Graph ingest/delta (PASS).  
**9E.1:** Personal Microsoft accounts (MSA) File Picker via `OneDrive.ReadOnly` + `https://onedrive.live.com/picker`. SharePoint document libraries, Teams files, and site crawling remain **out of scope**.

---

## 1. What you get

| Capability | Behavior |
|------------|----------|
| App catalog | Free published app slug `microsoft-onedrive`, connector key `microsoft_onedrive` |
| Auth | OAuth 2.0 authorization code + PKCE (Entra), offline refresh |
| Scopes (work-only tenant) | `openid profile offline_access User.Read Files.Read` |
| Scopes (`common` / `consumers`) | Same Graph scopes on connect (do **not** mix `OneDrive.ReadOnly` into authorize) |
| File pick (work/school) | File Picker v8 on `{tenant}-my.sharepoint.com` + SharePoint-audience token |
| File pick (personal) | File Picker v8 at `https://onedrive.live.com/picker` + separately minted `OneDrive.ReadOnly` token |
| Ingest | PDF, TXT, Markdown; Office via Graph PDF conversion |
| Sync | Graph driveItem **delta** + root-drive change notifications; Celery Beat renews subscriptions |

---

## 2. Prerequisites

1. Microsoft Entra ID app registration (Azure portal) with admin consent for the org if required.
2. Geem API + worker + Redis + Postgres ([development.md](../development.md)).
3. **Publicly reachable** `APP_URL` for Graph webhook validation/notifications.
4. SPA origin in `CORS_ORIGINS` matching `WORKSPACE_WEB_URL` / Vite.

---

## 3. Entra app registration

1. Azure Portal → **Microsoft Entra ID → App registrations → New registration**.
2. Name: e.g. `Geem OneDrive`.
3. Supported account types:
   - **Dual-account (9E.1):** Accounts in any organizational directory **and** personal Microsoft accounts.
   - **Work-only:** Accounts in any organizational directory (matches `MICROSOFT_ONEDRIVE_TENANT=organizations`).
4. Redirect URI (Web):
   - `{APP_URL}/api/connectors/oauth/microsoft_onedrive/callback`
   - Example local: `http://api.geem.dm:8000/api/connectors/oauth/microsoft_onedrive/callback`
5. Create a **client secret**; store only in env (never commit).
6. Note **Application (client) ID**.

---

## 4. API permissions (delegated)

Add Microsoft Graph **delegated** permissions:

| Permission | Why |
|------------|-----|
| `openid` / `profile` / `offline_access` | Sign-in + refresh |
| `User.Read` | Account display / identity |
| `Files.Read` | Read selected OneDrive driveItems + delta |

For **work/school File Picker**, also add SharePoint delegated **`MyFiles.Read`** (or ensure the app can acquire SharePoint-host tokens after consent).

For **personal File Picker**, Geem mints a separate token with runtime scope **`OneDrive.ReadOnly`** against the `consumers` authority after connect (when `MICROSOFT_ONEDRIVE_TENANT` is `common` or `consumers`). That scope is **not** added to the authorize URL — mixing it with Graph scopes breaks personal Microsoft account code exchange. Entra maps consented Graph **`Files.Read`** to the consumer picker token. If picker mint returns `invalid_scope` / consent required, **Reconnect**.

Do **not** request `Files.ReadWrite*`, `Files.Read.All`, or `Sites.Read.All` for 9E/9E.1.

---

## 5. Geem API environment

```bash
MICROSOFT_ONEDRIVE_CLIENT_ID=
MICROSOFT_ONEDRIVE_CLIENT_SECRET=
# Empty → {APP_URL}/api/connectors/oauth/microsoft_onedrive/callback
MICROSOFT_ONEDRIVE_REDIRECT_URI=
# common = work/school + personal | organizations = work-only | consumers | <tenant-guid>
MICROSOFT_ONEDRIVE_TENANT=common
# Graph subscription lifetime minutes (< ~42300)
MICROSOFT_ONEDRIVE_SUBSCRIPTION_MINUTES=4000
```

Also required: `APP_URL`, `WORKSPACE_WEB_URL`, `SECRETS_ENCRYPTION_KEY`, `REDIS_URL`, `CORS_ORIGINS`.

Restart API **and** Celery worker after changing these (both register the adapter).

---

## 6. Verify availability

`GET /api/apps/microsoft-onedrive` (Workspace auth) → `connector.available === true` when credentials are set.

---

## 7. In-product flow

1. `/apps/microsoft-onedrive` → Install → **Connect Microsoft OneDrive**.
2. Complete Entra consent → connection `active` with encrypted credentials + `account_kind` (`work_school` | `personal`).
3. Expert → Knowledge → **Add from Microsoft OneDrive** → File Picker v8 → select files.
4. Backend revalidates Graph metadata (`drive_id` + `item_id`), creates `ConnectorItem` + Expert source, enqueues sync.
5. Content → existing Document ingest → MinIO + Qdrant (Expert-filtered).
6. Delta + Graph notifications keep tracked files fresh; **Sync now** triggers a manual run.

---

## 8. Identity & security notes

| Item | Rule |
|------|------|
| External id | `{drive_id}:{item_id}` — never path/filename |
| Credentials | Encrypted on `app_connections`; refresh tokens never sent to React |
| Picker tokens | Memory-only; `picker-session` / `picker-token`; backend mint for both account kinds |
| `clientState` / `deltaLink` | Encrypted sync state only |
| Download URLs | Preauthenticated Graph URLs never persisted |
| Disconnect | Best-effort subscription delete; secrets cleared; sources unavailable |

---

## 9. Related code

| Area | Path |
|------|------|
| Adapter | `apps/api/app/connectors/providers/microsoft_onedrive/` |
| Shared knowledge ingest | `apps/api/app/connectors/knowledge/` |
| Expert sources API | `POST /api/experts/{id}/connector-sources` |
| Webhooks | `/api/connectors/webhooks/microsoft_onedrive/{routing_token}` |
| SPA picker | `apps/workspace_web/src/features/apps/microsoft-onedrive/picker.ts` |
| Picker auth | `apps/api/app/connectors/providers/microsoft_onedrive/picker_auth.py` |
| Tests | `apps/api/tests/integration/test_microsoft_onedrive_phase9e.py` |

---

## 10. Troubleshooting

| Symptom | Check |
|---------|--------|
| `microsoft_onedrive_not_configured` | Client id/secret set; API+worker restarted |
| Reauthorization required / personal picker fails | Confirm Entra has Graph `Files.Read`; `MICROSOFT_ONEDRIVE_TENANT=common`; **Reconnect** if mint returns consent/`invalid_scope` |
| Connect fails with “authorization failed” (MSA) | Do not put `OneDrive.ReadOnly` on authorize — Graph-only connect; check redirect URI matches `{APP_URL}/api/connectors/oauth/microsoft_onedrive/callback` |
| Work/school picker fails with SharePoint audience | Add SharePoint `MyFiles.Read`; confirm drive webUrl is `*-my.sharepoint.com` |
| Personal picker shows `unableToObtainToken` | Backend must allow `api.onedrive.com` authenticate resources; picker-session OK but picker-token 422 means host allowlist — check API logs `resource_host` |
| “Selected file is not from the connected OneDrive” (personal) | MSA drive ids are case-insensitive — fixed by Graph revalidation; retry pick. Shared/other drives still rejected |
| SPA logs out when opening Picker | Provider auth errors are 403 (not session 401). Hard-refresh Workspace |
| Picker popup blocked | Allow popups for the Workspace origin |
| Webhooks never fire (especially MSA) | Public `APP_URL`; validationToken handshake; use **Sync now** if MSA notifications are flaky |
| SharePoint library / Teams files | Expected — OneDrive personal/business files only |
