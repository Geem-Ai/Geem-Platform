# Phase 9 — App Store acceptance checklist

Status tracking for Geem App Store slices **9A–9G**. Mark **PASS** only when backed by automated tests or explicit manual verification.

## 9A — App Store Core

| Check | Evidence | Status |
|-------|----------|--------|
| Global catalog list/detail | `test_apps_catalog_phase9a.py` | PASS |
| Free install / uninstall | `test_apps_catalog_phase9a.py`, `test_apps_management_phase9g.py` | PASS |
| Access gating (`AppAccessService`) | 9A/9B access matrix + 9G edge cases | PASS |
| Role browse vs manage | 9A + 9G role matrix | PASS |
| Encrypted installation config never in API | 9A + 9G secrecy sweep | PASS |

## 9B — App Billing & Plans

| Check | Evidence | Status |
|-------|----------|--------|
| One-time purchase → license | `test_apps_billing_phase9b.py` | PASS |
| License survives uninstall / reinstall free | 9B + 9G one-time edge | PASS |
| Subscription checkout + period math | 9B | PASS |
| Manual renew (active extend / expired from now) | 9B + 9G WhatsApp expire/renew | PASS |
| Payment-return idempotency | 9B + 9G renew replay | PASS |
| Billing history App kinds | API PurchaseOut + UI labels EN/AR | PASS |

## 9C — Connector Foundation

| Check | Evidence | Status |
|-------|----------|--------|
| Connection lifecycle + encrypted credentials | `test_connectors_phase9c.py` | PASS |
| OAuth state one-time / workspace-bound | 9C | PASS |
| Connection entitlement limits | 9C + 9G usage DTO | PASS |
| Webhook idempotency + Celery tenant context | 9C | PASS |

## 9D — Google Drive

| Check | Evidence | Status |
|-------|----------|--------|
| OAuth + picker (no refresh token in picker DTO) | `test_google_drive_phase9d.py` | PASS |
| Expert connector source → ingest path | 9D + 9G free E2E | PASS |
| Workspace isolation | 9D | PASS |

## 9E / 9E.1 — Microsoft OneDrive

| Check | Evidence | Status |
|-------|----------|--------|
| Work/school Graph path | `test_microsoft_onedrive_phase9e.py` | PASS |
| Personal `account_kind` + picker mint | 9E.1 coverage in 9E suite | PASS |
| Member cannot connect | 9E | PASS |

## 9F — WhatsApp / OpenWA

| Check | Evidence | Status |
|-------|----------|--------|
| Published SAR plans `line` / `desk` / `ops` | seed + 9G paid E2E | PASS |
| QR / pairing connect | `test_openwa_phase9f.py` | PASS |
| Expert binding + inbound/outbound | 9F | PASS |
| Webhook HMAC + idempotency | 9F | PASS |
| Expired subscription fails closed | 9F + 9G expire/renew | PASS |

## 9G — App Management + E2E Gate

| Check | Evidence | Status |
|-------|----------|--------|
| `/apps` access badges (Free/Purchased/Subscribed/Installed/Expired/Coming soon) | UI + Vitest badge resolver | PASS |
| `/apps/:slug` access edge states + renew | UI + AppsPage / subscription status tests | PASS |
| `/apps/installed` plan/period/usage/renew | InstalledAppCard + API usage DTO | PASS |
| Connection health + X of Y usage | Connections panel + DTO | PASS |
| Billing history App labels EN/AR | `formatPurchaseHistoryTitle` + locales | PASS |
| EN / AR / RTL copy for Phase 9 Apps | locales en/ar | PASS |
| DTO secrecy regression | `TestDtoSecrecy` in 9G | PASS |
| Workspace isolation (WhatsApp connections) | 9G isolation | PASS |
| Owner/Admin/Member matrix | 9G role matrix + frontend member UX | PASS |
| Free E2E: install → connect → Expert source | `TestE2EFreeDrive` | PASS |
| Paid WhatsApp E2E: subscribe → install → connect | `TestE2EWhatsAppPaid` | PASS |
| Expired → renew restores access | `TestWhatsAppExpireRenew` | PASS |
| Browser smoke (catalog / installed / member / WhatsApp plans) | `apps/workspace_web` Playwright `e2e/apps-smoke.spec.ts` + API E2E gate | PASS |

## Gate summary

- **9A–9F regression:** `pytest` Phase 9 integration suites — PASS (110 tests in combined run)
- **9G management suite:** `test_apps_management_phase9g.py` — PASS (11 tests)
- **workspace_web Apps Vitest:** PASS (66 tests)
- **Playwright Apps smoke:** `npm run test:e2e` — PASS (4 tests)
- **workspace_web typecheck/build:** PASS

**Phase 9 overall:** COMPLETE
