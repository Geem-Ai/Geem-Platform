import type { PurchaseStatus } from '@/services/api/billing';

export const PURCHASE_STATUSES = [
  'pending',
  'redirected',
  'paid',
  'failed',
  'cancelled',
  'expired',
] as const;

export type KnownPurchaseStatus = (typeof PURCHASE_STATUSES)[number];

export function purchaseStatusLabelKey(status: string): string {
  if (PURCHASE_STATUSES.includes(status as KnownPurchaseStatus)) {
    return `billing.status.${status}`;
  }
  return 'billing.status.unknown';
}

export function purchaseStatusBadgeVariant(
  status: PurchaseStatus,
): 'success' | 'warning' | 'destructive' | 'secondary' {
  if (status === 'paid') return 'success';
  if (status === 'pending' || status === 'redirected') return 'warning';
  if (status === 'failed' || status === 'cancelled' || status === 'expired') {
    return 'destructive';
  }
  return 'secondary';
}

export function purchaseKindLabelKey(kind: string): string {
  if (kind === 'subscription') return 'billing.kind.subscription';
  if (kind === 'credit_pack') return 'billing.kind.creditPack';
  if (kind === 'app_one_time') return 'billing.kind.appOneTime';
  if (kind === 'app_subscription') return 'billing.kind.appSubscription';
  if (kind === 'app_subscription_renewal') return 'billing.kind.appRenewal';
  return 'billing.kind.other';
}

/** Human label for billing history rows — prefer App name + action when available. */
export function formatPurchaseHistoryTitle(
  item: {
    kind: string;
    item_name?: string | null;
    app_name?: string | null;
  },
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const appName = item.app_name?.trim();
  if (appName && item.kind === 'app_one_time') {
    return t('billing.kind.appOneTimeNamed', { app: appName });
  }
  if (appName && item.kind === 'app_subscription') {
    return t('billing.kind.appSubscriptionNamed', { app: appName });
  }
  if (appName && item.kind === 'app_subscription_renewal') {
    return t('billing.kind.appRenewalNamed', { app: appName });
  }
  if (item.item_name?.trim()) {
    return item.item_name.trim();
  }
  return t(purchaseKindLabelKey(item.kind));
}

export function isPaidStatus(status: string): boolean {
  return status === 'paid';
}

export function isFailedStatus(status: string): boolean {
  return status === 'failed' || status === 'cancelled' || status === 'expired';
}

export function isPendingStatus(status: string): boolean {
  return status === 'pending' || status === 'redirected';
}
