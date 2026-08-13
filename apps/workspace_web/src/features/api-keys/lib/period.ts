import type { ApiUsagePeriodKey } from '@/services/api/api-keys';

export const API_USAGE_PERIODS: ApiUsagePeriodKey[] = ['24h', '7d', '30d'];

export function parseApiUsagePeriod(raw: string | null | undefined): ApiUsagePeriodKey {
  if (raw === '24h' || raw === '7d' || raw === '30d') return raw;
  return '30d';
}

export function parseApiUsagePage(raw: string | null | undefined): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.floor(n);
}

export function apiUsageHref(
  period: ApiUsagePeriodKey,
  keyId: string | null,
  page: number,
): string {
  const qs = new URLSearchParams();
  qs.set('period', period);
  if (keyId) qs.set('key', keyId);
  if (page > 1) qs.set('page', String(page));
  return `/api/usage?${qs.toString()}`;
}
