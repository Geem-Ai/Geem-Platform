# WhatsApp / OpenWA channel — configuration A–Z

End-to-end setup for Geem’s **WhatsApp** channel connector (Phase 9F) via **OpenWA**
(unofficial WhatsApp gateway). This is **not** Meta’s official WhatsApp Cloud API.

> **Risk notice:** OpenWA is an unofficial WhatsApp integration. Account restrictions
> or bans are possible. Use dedicated business/automation numbers — never a primary
> personal number.

Without `OPENWA_BASE_URL` and `OPENWA_API_KEY`, the adapter stays registered but
`available=false` (`openwa_not_configured`). Catalog app `whatsapp` is **published**
with monthly SAR subscription plans (`line` / `desk` / `ops`). Install still requires
an active App subscription period, and connecting sessions requires OpenWA configured.

---

## 1. Architecture

```text
Workspace
  → WhatsApp App subscription (AppAccessService)
  → App installation
  → OpenWA session / app_connection
  → channel_bindings (Expert + auto-reply + groups)
  → inbound message.received webhook
  → channel conversation + ChatTurnExecutor
  → Workspace AI quota
  → OpenWA send-text
```

There is **no separate AI pipeline**. WhatsApp reuses Expert/RAG/model/metering
boundaries used by Workspace Chat and the public API.

---

## 2. OpenWA API contract (discovered)

**Authoritative source:** live Swagger at `https://whatsapp-hub.dalseen.sa/api/docs`
(OpenWA API **0.15.0**, OAS 3.0). Flow/behavior reference only:
[session-connect-until-ready](https://github.com/MustafaTaj/OpenWA/blob/main/docs/examples/session-connect-until-ready.md).

**Base URL (Geem):** `OPENWA_BASE_URL=https://whatsapp-hub.dalseen.sa`  
Do **not** treat `/api/docs` as an API base path.

**Auth header:** `X-API-Key: <OPENWA_API_KEY>` (global security scheme).

### Implementation matrix (Geem subset)

| Geem operation | Method | Path | Notes |
|----------------|--------|------|-------|
| Create session | `POST` | `/api/sessions` | Body `{ "name": "..." }` — name `^[a-zA-Z0-9-]+$`, length 3–50 |
| List sessions | `GET` | `/api/sessions` | Not used by Geem routinely |
| Get session | `GET` | `/api/sessions/{id}` | Status + phone + pushName + lastError + engineLoaded |
| Start session | `POST` | `/api/sessions/{id}/start` | → `initializing` / `qr_ready` / `ready` |
| Get QR | `GET` | `/api/sessions/{id}/qr` | `{ qrCode, status }` data URL |
| Pairing code | `POST` | `/api/sessions/{id}/pairing-code` | `{ phoneNumber }` → `{ pairingCode, status }` |
| Logout | `POST` | `/api/sessions/{id}/logout` | Unlinks linked device |
| Delete session | `DELETE` | `/api/sessions/{id}` | Removes session resources |
| Stop | `POST` | `/api/sessions/{id}/stop` | **Not** used for Geem disconnect (preserves auth) |
| Create webhook | `POST` | `/api/sessions/{sessionId}/webhooks` | url, events, secret |
| List webhooks | `GET` | `/api/sessions/{sessionId}/webhooks` | Idempotent reconcile |
| Get webhook | `GET` | `/api/sessions/{sessionId}/webhooks/{id}` | |
| Update webhook | `PUT` | `/api/sessions/{sessionId}/webhooks/{id}` | |
| Delete webhook | `DELETE` | `/api/sessions/{sessionId}/webhooks/{id}` | |
| Send text | `POST` | `/api/sessions/{sessionId}/messages/send-text` | `{ chatId, text }` — text max **4096** |

### Session status enum (Swagger)

`created` · `initializing` · `qr_ready` · `authenticating` · `ready` ·
`disconnected` · `action_required` · `failed`

Unknown future statuses must not crash Geem; map to unavailable/error UX and keep
the raw provider value for diagnostics.

### Pairing phone format

Digits only, international, no `+` / spaces / hyphens, typically 6–15 digits
(e.g. `9665XXXXXXXX`). No country hardcoding.

### Webhook registration payload

```json
{
  "url": "https://{APP_URL}/api/connectors/webhooks/openwa/{routingToken}",
  "events": [
    "message.received",
    "session.status",
    "session.authenticated",
    "session.disconnected",
    "session.restriction"
  ],
  "secret": "<per-connection HMAC secret>"
}
```

Do **not** subscribe to `"*"` unless a concrete requirement appears.

### Webhook security

| Header | Role |
|--------|------|
| `X-OpenWA-Signature` | `sha256=<hex>` HMAC-SHA256 over **raw body** |
| `X-OpenWA-Idempotency-Key` | Stable logical idempotency (Geem dedupe key) |
| `X-OpenWA-Delivery-Id` | Delivery attempt id — **do not** use for dedupe |
| `X-OpenWA-Event` | Event name |

Constant-time compare. Routing token ≠ `app_connection` UUID. Never trust
`workspace_id` / `expert_id` from the body — resolve tenancy via the connection
reached by the routing token.

### Inbound `message.received` (shape)

Normalized fields Geem uses: provider message id, `from` / chat id, `body`,
`type`, `isGroup`, `fromMe`, timestamp. Phase 9F supports **text** only.

---

## 3. Install vs subscription vs connection

| Layer | Meaning |
|-------|---------|
| Subscription | Commercial access via `AppAccessService` (period) |
| Installation | Workspace installed the WhatsApp App |
| Connection | One OpenWA session under the App’s `connections` entitlement |
| Channel binding | Expert + auto-reply + `respond_to_groups` for that connection |

Expired subscription → fail closed (no AI, no outbound). Geem does **not**
silently unlink the WhatsApp device on expiry. Signed inbound webhooks received
while the App is expired, uninstalled, or otherwise inactive trigger a
**best-effort OpenWA webhook delete** (session stays linked). Re-install /
subscription reactivation / session `ready` sync re-registers the webhook when
access is active again.

---

## 4. Required environment

```env
OPENWA_BASE_URL=https://whatsapp-hub.dalseen.sa
OPENWA_API_KEY=
OPENWA_TIMEOUT_SECONDS=30
```

`OPENWA_API_KEY` is backend-only. Never expose to `workspace_web`, logs, DTOs,
exceptions, or connection responses. The key must be unscoped OPERATOR-or-higher
so session create/start/webhook/message operations succeed.

Also required for production webhooks: publicly reachable `APP_URL`.

---

## 5. Session lifecycle (Geem)

1. Owner/admin Connect → create `app_connection` (`connecting`) + OpenWA session name
   `geem-{workspaceSlug}-{shortId}` (3–50, alphanumeric/hyphen).
2. `POST /api/sessions` → store provider session UUID.
3. `POST /api/sessions/{id}/start`.
4. Frontend polls **Geem** (~2s) — never OpenWA from the browser.
5. QR mode: when `qr_ready`, Geem fetches QR and returns a short-lived data URL.
6. Pairing mode: after `qr_ready`, Geem requests pairing code with normalized phone.
7. When `ready`: persist safe metadata, register signed webhook **only if App
   access is active**, mark connection active only after webhook registration
   succeeds (or after identity sync when access is inactive — webhook omitted).
8. Install / purchase activation hooks re-register webhooks for any already-ready
   sessions under the installation.
9. Never persist QR images or pairing codes.

---

## 6. Expert binding

Table `channel_bindings`: one Expert per connection, `auto_reply_enabled`,
`respond_to_groups` (default **false**). Expert must pass `ExpertAccessService`.
No Expert / disabled auto-reply → no LLM.

---

## 7. Channel conversations

WhatsApp senders are not Geem users. Conversations use `source=channel` with
nullable `user_id`, mapped via `channel_conversation_bindings` on
`(workspace_id, app_connection_id, external_chat_id, expert_id)`.

Personal `/chat` history stays user-isolated — channel threads do not appear
there.

---

## 8. Disconnect / reconnect

**Disconnect WhatsApp** means revoke/unlink:

1. Mark Geem connection inactive first (fail closed).
2. Delete/disable OpenWA webhook.
3. `POST .../logout` (unlink device).
4. `DELETE` session when appropriate.
5. Clear provider secrets from the connection.

Provider cleanup is best-effort; Geem stays disabled if OpenWA is unreachable.

**Reconnect** calls OpenWA `/start` when `engineLoaded` is false / restart is valid.
Avoid restart loops.

---

## 9. Known limitations (Phase 9F)

- Text inbound/outbound only (no media/OCR/voice).
- No Meta Cloud API, broadcasts, templates engine, or CRM.
- Catalog plans: `line` (79 SAR / 1 connection), `desk` (199 SAR / 3),
  `ops` (449 SAR / 10) — monthly, manual renew.
- Markdown sent as plain text; responses split at ≤4096 characters.
