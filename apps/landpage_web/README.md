# Geem Marketing Site (`landpage_web`)

Public Arabic-first marketing website for **Geem**.

## Stack

- Astro 7 (static HTML)
- TypeScript
- Tailwind CSS v4 (`@tailwindcss/vite`)
- `@astrojs/sitemap`
- Self-hosted IBM Plex Sans Arabic / IBM Plex Sans
- Minimal client JS (header, mobile menu, reveals, copy button)

## Commands

```bash
cp .env.example .env
npm install
npm run dev       # http://localhost:4321
npm run check
npm run build
npm run preview
npm run verify    # after build — SEO/RTL smoke checks on dist/
```

## Routes

| Path | Purpose |
|------|---------|
| `/` | Redirect to `/ar` |
| `/ar`, `/en` | Homepage |
| `/[locale]/about` | About Geem / DALSEEN |
| `/[locale]/contact` | Contact |
| `/[locale]/security` | Security / isolation |
| `/[locale]/privacy` | Privacy |
| `/[locale]/terms` | Terms |
| `/[locale]/pdpl` | PDPL notice |

## Environment

Public build-time variables (see `.env.example`):

- `PUBLIC_SITE_URL`
- `PUBLIC_WORKSPACE_URL` → Workspace Login
- `PUBLIC_SIGNUP_URL` → Start with Geem (defaults to `{WORKSPACE}/register`)
- `PUBLIC_CONTACT_URL` (optional)
- `PUBLIC_DOCS_URL` (optional footer link)
- `PUBLIC_API_BASE_URL` (placeholder in curl sample only)

## Docker

Cloudflare Tunnel overlay uses the **production** nginx image (`Dockerfile.prod`) on port **80** (published as host **4321**). Local Compose without the overlay still uses `npm run dev`.

UAT Cloudflare Tunnel: **https://landpage-uat.geem.ai** (see [docs/development.md](../../docs/development.md) § C).

Production static image:

```bash
docker build -f Dockerfile.prod -t geem-landpage .
```

Serve `dist/` from Nginx (aaPanel). See [docs/deployment.md](../../docs/deployment.md).

## Boundaries

- Do **not** import from `apps/workspace_web`, `apps/web`, or `samples/`
- Brand assets are vendored under `src/assets/`
- No analytics by default
- Independent of Phase 11 / Phase 12 work
