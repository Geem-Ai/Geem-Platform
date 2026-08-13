export type PurchaseKindFilter = 'all' | 'subscription' | 'credit_pack';
export type PurchaseStatusFilter =
  | 'all'
  | 'paid'
  | 'pending'
  | 'failed'
  | 'cancelled'
  | 'expired';

export function parsePurchaseKind(raw: string | null): PurchaseKindFilter {
  if (raw === 'subscription' || raw === 'credit_pack') return raw;
  return 'all';
}

export function parsePurchaseStatus(raw: string | null): PurchaseStatusFilter {
  if (
    raw === 'paid' ||
    raw === 'pending' ||
    raw === 'failed' ||
    raw === 'cancelled' ||
    raw === 'expired'
  ) {
    return raw;
  }
  return 'all';
}

export function historyPageHref(
  page: number,
  kind: PurchaseKindFilter,
  status: PurchaseStatusFilter,
): string {
  const qs = new URLSearchParams();
  if (page > 1) qs.set('page', String(page));
  if (kind !== 'all') qs.set('kind', kind);
  if (status !== 'all') qs.set('status', status);
  const encoded = qs.toString();
  return encoded ? `/billing/history?${encoded}` : '/billing/history';
}

/** UI pending maps to backend pending+redirected. Other statuses are exact. */
export function statusQueryValue(status: PurchaseStatusFilter): string | undefined {
  if (status === 'all') return undefined;
  return status;
}
