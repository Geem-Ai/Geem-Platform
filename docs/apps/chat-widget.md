# Chat Widget — configuration A–Z

Embeddable website chat widget for Geem (Phase **9H**). Monthly App Store
subscription; one widget instance grounded on a single Expert.

## 1. Architecture

```text
Workspace
  → Chat Widget app subscription (AppAccessService)
  → App installation
  → widget_instances (appearance + Expert + optional allowed_origins)
  → Public bootstrap / messages (no API key in the page)
  → ChatTurnExecutor + Workspace AI quota
```

Visitor sites load `geem-widget.js` with `data-widget-id`. The script never
receives a workspace API key.

## 2. Commercial

| Item | Value |
|------|--------|
| Catalog slug | `chat-widget` |
| Billing | `subscription` |
| Plan | `standard` — **199 SAR / month** |
| Entitlement | `widgets: 1` |
| Renew | Manual (same as WhatsApp) — no auto-charge |

Flow: browse → checkout (ClickPay/Noop) → install → configure → embed.

## 3. Configuration (Workspace)

`GET/PUT /api/apps/chat-widget/widget` (session + `apps.manage`):

- Bind one **Expert** (private RAG grounding)
- Appearance: title, subtitle, greeting, logo URL, locale (`ar`/`en`),
  position (`bottom-right` / `bottom-left`), primary/text colors
- Optional **`allowed_origins`**: exact `http`/`https` origins (no paths, no wildcards)
  - Empty / omitted → allow any Origin (demos)
  - Non-empty → `Origin` (else `Referer` origin) must match exactly or **403**
- Embed HTML snippet (script URL from `APP_URL` + `geem-widget.js`)

`POST /api/apps/chat-widget/widget/disconnect` disables the instance and uninstalls
the app (subscription period remains until expiry).

## 4. Public APIs

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/public/widgets/{id}/bootstrap` | Appearance only |
| POST | `/api/public/widgets/{id}/messages` | `{ message, session_id? }` → `{ answer, session_id }` (no RAG citations). `session_id` is an **HMAC-signed** token (store and resend it). Same session continues the thread (≤ **15** prior messages to the LLM; messages older than **1 hour** deleted; ≤ **50** user messages per session per UTC day, `WIDGET_SESSION_MAX_MESSAGES_PER_DAY`). |
| GET | `/geem-widget.js` | Built IIFE from `apps/widget` |

CORS for these paths is widget-scoped (not the Workspace SPA allowlist).
IP rate limiting applies to messages.

Expired / missing subscription, disabled widget, or unbound Expert → fail closed.

## 5. Embed snippet

```html
<script
  src="https://<api-host>/geem-widget.js"
  data-widget-id="<uuid>"
  data-locale="ar"
  async
></script>
```

Optional `data-api-base` overrides the API origin (defaults to the script host).
Appearance changes apply after save without editing the script tag.
Launcher uses `/geem-animated.svg` (same waving Geem mascot as Workspace Chat).
Assistant replies render **GitHub-flavored Markdown** (headings, lists, links, code, tables) with HTML sanitization; visitor messages stay plain text.
The embed script keeps `session_id` in `sessionStorage` so a tab refresh continues the same thread.
Visitor messages are hard-deleted after `WIDGET_MESSAGE_TTL_HOURS` (default **1**): eagerly on the next message for that thread, and via Celery Beat `purge_expired_widget_messages` every 15 minutes for abandoned sessions. Empty widget conversations (and bindings) are removed after purge.
Each `session_id` is capped at `WIDGET_SESSION_MAX_MESSAGES_PER_DAY` (default **50**) user messages per UTC day. Configure `allowed_origins` in production; treat `session_id` as a secret (signed with `JWT_SECRET`).

## 6. Build the script

```bash
cd apps/widget && npm install && npm run build
```

Copies `dist/geem-widget.js` → `apps/api/app/widgets/static/geem-widget.js`.

## 7. Out of scope (v1)

- Multi-Expert grounding
- Wildcard origins (`*.example.com`)
- Auto-renew / Stripe
- Cross-device / long-lived visitor history UI (server threads exist per `session_id` but are not listed in Workspace Chat)
