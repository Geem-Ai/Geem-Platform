# Microsoft OneDrive app — configuration A–Z

End-to-end setup for Geem’s **Microsoft OneDrive** knowledge connector (Phase 9E): Entra app registration → Graph OAuth → File Picker v8 → Geem env → Workspace install → Expert knowledge.

Without `MICROSOFT_ONEDRIVE_CLIENT_ID` and `MICROSOFT_ONEDRIVE_CLIENT_SECRET`, the adapter stays registered but `available=false` (`microsoft_onedrive_not_configured`). Install/browse still work; Connect and OAuth do not.

**9E scope:** Microsoft **work/school** OneDrive (tenant default `organizations`). Personal Microsoft accounts may connect via Graph when `MICROSOFT_ONEDRIVE_TENANT=common`, but **File Picker v8 is work/school only** (SharePoint-audience tokens). SharePoint document libraries, Teams files, and site crawling are **out of scope**.

---

## 1. What you get

| Capability | Behavior |
|------------|----------|
| App catalog | Free published app slug `microsoft-onedrive`, connector key `microsoft_onedrive` |
| Auth | OAuth 2.0 authorization code + PKCE (Entra), offline refresh |
| Scopes | `openid profile offline_access User.Read Files.Read` (read-only) |
| File pick | Microsoft File Picker **v8** (popup + postMessage) |
| Ingest | PDF, TXT, Markdown; Office (doc/docx/ppt/pptx/xls/xlsx) via Graph PDF conversion |
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
3. Supported account types: **Accounts in any organizational directory** (matches `MICROSOFT_ONEDRIVE_TENANT=organizations`). Use `common` / `consumers` / a specific tenant ID later without code redesign.
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

Do **not** request `Files.ReadWrite*`, `Files.Read.All`, or `Sites.Read.All` for 9E.

File Picker v8 needs a **SharePoint-host audience** token (not Graph) for both bootstrap (`…/picker-session`) and authenticate (`…/picker-token`). Geem mints those from the backend refresh token for the connected `{tenant}-my.sharepoint.com` host only (fail closed if the drive web URL is unknown). Rotated refresh tokens from those exchanges are persisted without replacing the Graph `access_token`. Ensure the Entra app can acquire `Files.Read` (or SharePoint `MyFiles.Read`) against that resource after admin consent if your tenant requires it.

---

## 5. Geem API environment

```bash
MICROSOFT_ONEDRIVE_CLIENT_ID=
MICROSOFT_ONEDRIVE_CLIENT_SECRET=
# Empty → {APP_URL}/api/connectors/oauth/microsoft_onedrive/callback
MICROSOFT_ONEDRIVE_REDIRECT_URI=
# organizations | common | consumers | <tenant-guid>
MICROSOFT_ONEDRIVE_TENANT=organizations
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
2. Complete Entra consent → connection `active` with encrypted credentials + drive identity.
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
| Picker tokens | Memory-only SharePoint-audience; `picker-session` / `picker-token` |
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
| Reauthorization required | User revoked consent / missing refresh token — Connect again |
| `microsoft_onedrive_drive_not_supported` / picker fails on personal Hotmail/Outlook | Phase 9E File Picker requires **work/school** OneDrive (`*-my.sharepoint.com`). Personal MSA (`microsoftpersonalcontent.com` / `onedrive.live.com`) can connect for Graph health but cannot open Picker. Set `MICROSOFT_ONEDRIVE_TENANT=organizations` and reconnect with a work account. |
| SPA logs out when opening Picker | Fixed: provider auth errors are 403 (not session 401). Rebuild/reload Workspace if you still see logout. |
| Picker popup blocked | Allow popups for the Workspace origin |
| Webhooks never fire | Public `APP_URL`; validationToken handshake; subscription renewal Beat task |
| SharePoint rejected | Expected — 9E is OneDrive only |
