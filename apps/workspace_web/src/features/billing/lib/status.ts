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
  return 'billing.kind.other';
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
