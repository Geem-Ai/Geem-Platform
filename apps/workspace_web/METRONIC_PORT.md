# Metronic port record — Geem Workspace Web

## Source

| Item | Value |
|------|--------|
| Metronic version | **9.5.0** |
| Sample path (read-only) | `samples/metronic_vite_9.5.0` |
| Concept | AI Concept only (`src/ai/**` + traced shared deps) |
| Port date | 2026-08-11 |

**Rule:** There is **no runtime dependency** on `samples/`. Upgrades are manual selective ports. Never `npm link` or path-import the sample.

## AI Concept source paths used (adapted)

Phase 0A established shell/layout infrastructure inspired by:

- `src/ai/layout/index.tsx` → `src/app/layouts/workspace/index.tsx`
- `src/ai/layout/components/context.tsx` → `context.tsx`
- `src/ai/layout/components/wrapper.tsx` → `wrapper.tsx`
- `src/ai/layout/components/sidebar.tsx` → `sidebar.tsx`
- `src/ai/layout/components/sidebar-header.tsx` → `sidebar-header.tsx` (Geem brand)
- `src/ai/layout/components/sidebar-content.tsx` → product nav (not mock chats)
- `src/ai/layout/components/sidebar-footer.tsx` → account + workspace placeholders
- `src/ai/layout/components/header.tsx` → mobile header + Sheet
- `src/App.tsx` theme/toaster shell → `src/app/providers/`

Chat UI pages/components from `src/ai/pages/**` and `src/ai/components/**` are partially adapted in Phase 3C. Stateless Ask UI (`AskExpertPage`, `ChatShell`, `ExpertSelector`, `Composer`) is implemented using the AI Concept starter/chat layout pattern without porting mock/history data. Full conversation persistence and `MessageList` patterns are Phase 4.

## Shared components ported

From `samples/metronic_vite_9.5.0/src/components/ui/`:

- `avatar.tsx`
- `badge.tsx`
- `button.tsx`
- `card.tsx`
- `dialog.tsx`
- `dropdown-menu.tsx`
- `input.tsx`
- `scroll-area.tsx`
- `separator.tsx`
- `sheet.tsx`
- `tooltip.tsx`
- `sonner.tsx`

Also:

- `src/hooks/use-mobile.tsx` → `src/hooks/use-mobile.ts`
- `src/lib/utils.ts` (`cn`)
- `src/lib/helpers.ts` (`toAbsoluteUrl` only; other helpers not required)
- `src/components/screen-loader.tsx` → `src/components/shared/ScreenLoader.tsx` (Geem avatar)
- Theme tokens from `src/styles/globals.css` + `config.metronic.css` (font size tokens only; **no** `demos/demo1.css`)

## Packages introduced

Production stack aligned with the approved plan:

- `react`, `react-dom` (19.x)
- `vite` 7 + `@vitejs/plugin-react`
- `typescript`
- `react-router` / `react-router-dom` 7
- `tailwindcss` 4 + `@tailwindcss/vite` + `tw-animate-css`
- `lucide-react`
- `next-themes` (storage key: `geem-theme`)
- `sonner`
- `react-helmet-async` (**v3** — Metronic sample pins v2; v3 required for React 19 peerDeps)
- `class-variance-authority`, `clsx`, `tailwind-merge`
- `radix-ui` (unified package used by Metronic shadcn primitives)
- `@tanstack/react-query`
- `i18next`, `react-i18next`
- `react-markdown`, `remark-gfm` (wired in Phase 3C Ask Expert / MessageRenderer)

## Phase 3C — Experts UX + Stateless Ask Expert

Adapted AI Concept patterns (no sample imports, no mock data):

- Expert selector cards inspired by starter/persona selection language
- Composer + streamed message rendering for `/chat?expert=`
- Citation list (metadata-only; Platform citations never link to raw Documents)
- Dialog/Sheet patterns already ported for upload + confirmations

Still deferred to Phase 4: conversation persistence, recent/pinned chats, Metronic `chat-message` / `chat-starter*` full chrome, history sidebar.

## Intentionally excluded

- Entire `src/ai/mock/**` (no demo data / fake chat replies)
- Full AI chat history chrome (`chat-message`, `chat-starter*`, pinned/recent) — Phase 4
- Dead AI files: `model-selector.tsx`, `new-chat-context.tsx`
- `chats-context.tsx`, pinned/recent chats, AI model selector as product logic
- Demo auth / fake user avatars (`300-2.png`, KeenAI logos)
- Concepts: CRM, Mail, Calendar, Todo, Real Estate, Store Inventory
- `modules-provider.tsx` multi-demo router
- `src/styles/demos/**`
- Unrelated Metronic deps (apexcharts, leaflet, formik, dnd-kit, vaul, cmdk, etc.)
- Most of `public/media/**`

## Branding

- Product: **Geem**
- Avatar vendored: `public/brand/geem-avatar.webp` (source of truth URL: `https://geem.ai/assets/geem-avatar.webp`)
- Theme storage key: `geem-theme`
- Locale storage key: `geem-locale`
