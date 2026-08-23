import type { TFunction } from 'i18next';
import type { PlatformPurchaseTarget } from '@/services/api/types';

const APP_PURCHASE_KINDS = new Set([
  'app_one_time',
  'app_subscription',
  'app_subscription_renewal',
]);

export function purchaseStatusLabel(t: TFunction, status: string): string {
  const key = `purchases.status.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}

export function purchaseKindLabel(t: TFunction, kind: string): string {
  const key = `purchases.kinds.${kind}`;
  const translated = t(key);
  return translated === key ? kind : translated;
}

export function isAppPurchaseKind(kind: string): boolean {
  return APP_PURCHASE_KINDS.has(kind);
}

export function purchaseAppHref(target: PlatformPurchaseTarget): string | null {
  if (target.app_id) {
    return `/app-store/${target.app_id}`;
  }
  if (target.app_slug) {
    return `/app-store?search=${encodeURIComponent(target.app_slug)}`;
  }
  return null;
}

export function purchaseProductLabel(target: PlatformPurchaseTarget): string {
  if (target.app_name && target.item_name && target.item_name !== target.app_name) {
    return target.item_name;
  }
  return target.item_name ?? target.app_name ?? target.item_code ?? '—';
}
