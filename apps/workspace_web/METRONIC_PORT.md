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
- `alert-dialog.tsx` (ReUI / Metronic confirm dialog — used for destructive logout)
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
- `react-markdown`, `remark-gfm` (wired in Phase 3C Ask Expert / MessageRenderer; Phase 4C Chat bubbles)

## Phase 3C — Experts UX + Stateless Ask Expert

Adapted AI Concept patterns (no sample imports, no mock data):

- Expert selector cards inspired by starter/persona selection language
- Composer + streamed message rendering for `/chat?expert=`
- Citation list (metadata-only; Platform citations never link to raw Documents)
- Dialog/Sheet patterns already ported for upload + confirmations

### Experts create/edit/view Sheets (visual pattern only)

Adapted from Metronic **store-inventory** product list interaction (read-only reference):

- `samples/.../store-inventory/pages/components/product-form-sheet.tsx`
- `samples/.../store-inventory/pages/components/product-details-analytics-sheet.tsx`
- `samples/.../store-inventory/pages/tables/product-list.tsx`

Ported into Geem as:

- `features/experts/components/ExpertFormSheet.tsx` (create + edit)
- `features/experts/components/ExpertDetailSheet.tsx` (view)

Pattern kept: list page stays mounted; floating inset `Sheet` (`inset-5`, rounded, header/body/footer) opens for add/edit/view. Inventory domain (SKU, stock, variants, charts) was **not** ported.

Phase 3C stateless Ask UI was replaced by Phase 4C persisted Chat (below).

## Phase 4C — Production Metronic AI Chat UX

Selectively adapted from `samples/metronic_vite_9.5.0/src/ai/**` into `features/chat/**` (no runtime sample imports, zero mock chat state):

| Sample reference | Production |
|------------------|------------|
| `chat-starter*` | `ChatStarter.tsx` + `ChatComposer.tsx` + `ExpertSelector.tsx` |
| `chat-message` / `chat-messages` | `ChatMessage.tsx` / `ChatMessages.tsx` (+ `react-markdown`, Geem avatar) |
| `recent-chats` / `pinned-chats` / `new-chat-button` | `ConversationLists.tsx` / `NewChatButton.tsx` (primary→purple animated gradient) in workspace sidebar |
| `quick-actions.tsx` | `features/chat/components/QuickActions.tsx` (Favorites, Clear History; Templates → Soon) |
| `user-dropdown-menu.tsx` | `account-menu.tsx` profile card + workspace switcher in dropdown |
| Chat vs product nav | `sidebarMode` in `layouts/workspace/context.tsx` — chat mode vs Workspace settings (`workspaceNav`) |
| `pages/start.tsx` / `pages/chat.tsx` | `ChatStartPage.tsx` (`/chat`) / `ChatPage.tsx` (`/chat/:conversationId`) |
| Share dialog / model selector | **Not ported** (no backend share; Experts replace models) |

Production data: Conversations REST + SSE (`useChatStream`), Workspace-scoped React Query keys, pin/favorite/rename/delete mutations.

## Intentionally excluded

- Entire `src/ai/mock/**` (no demo data / fake chat replies)
- Dead AI files: `model-selector.tsx`, `new-chat-context.tsx`
- `chats-context.tsx`, AI model selector as product logic
- Demo auth / fake user avatars (`300-2.png`, KeenAI logos, `logo-34.svg`)
- Concepts: CRM, Mail, Calendar, Todo, Real Estate, Store Inventory (except Sheet interaction pattern already noted in 3C)
- `modules-provider.tsx` multi-demo router
- `src/styles/demos/**`
- Unrelated Metronic deps (apexcharts, leaflet, formik, dnd-kit, vaul, cmdk, etc.)
- Most of `public/media/**`
- Fake share dialog

## Branding

- Product: **Geem**
- Avatar vendored: `public/brand/geem-avatar.webp` (source of truth URL: `https://geem.ai/assets/geem-avatar.webp`)
- Chat mascot: `public/brand/geem-animated.svg` (waving SVG; used via `GeemAnimatedMascot` on Chat starter + assistant bubbles)
- Theme storage key: `geem-theme`
- Locale storage key: `geem-locale`
