export function apiUsageDayKey(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function apiUsageDayBucket(
  iso: string,
  now = new Date(),
): 'today' | 'yesterday' | 'other' {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'other';
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startTarget = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round(
    (startToday.getTime() - startTarget.getTime()) / 86_400_000,
  );
  if (diffDays === 0) return 'today';
  if (diffDays === 1) return 'yesterday';
  return 'other';
}

export function groupApiUsageByDay<T extends { created_at: string }>(
  items: T[],
): { key: string; items: T[] }[] {
  const groups: { key: string; items: T[] }[] = [];
  const index = new Map<string, T[]>();
  for (const item of items) {
    const key = apiUsageDayKey(item.created_at);
    const existing = index.get(key);
    if (existing) {
      existing.push(item);
      continue;
    }
    const next = [item];
    index.set(key, next);
    groups.push({ key, items: next });
  }
  return groups;
}
