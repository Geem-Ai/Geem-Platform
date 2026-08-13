import { STORAGE_PAGE_SIZE } from '@/services/api/documents';

export { STORAGE_PAGE_SIZE };

export function parseStoragePage(raw: string | null): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.floor(n);
}

export function storagePageHref(page: number, q = ''): string {
  const params = new URLSearchParams();
  if (page > 1) params.set('page', String(page));
  const query = q.trim();
  if (query) params.set('q', query);
  const qs = params.toString();
  return qs ? `/storage?${qs}` : '/storage';
}
