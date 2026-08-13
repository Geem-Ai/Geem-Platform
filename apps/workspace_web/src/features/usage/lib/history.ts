import type { UsageHistoryItem, UsageHistoryKind } from '@/services/api/usage';
import { isAiHistoryKind } from '@/services/api/usage';


export type HistoryKindFilter = 'all' | 'ai' | 'credits';

export type HistoryDatePreset = 'all' | 'today' | '7d' | '30d' | 'custom';

export type HistoryDateRange = {
  from?: string | null;
  to?: string | null;
};

export const HISTORY_KIND_FILTERS: readonly HistoryKindFilter[] = [
  'all',
  'ai',
  'credits',
];

export const HISTORY_DATE_PRESETS: readonly Exclude<HistoryDatePreset, 'custom'>[] =
  ['all', 'today', '7d', '30d'];

export function parseHistoryKind(raw: string | null): HistoryKindFilter {
  if (raw === 'ai' || raw === 'ai_tokens') return 'ai';
  if (raw === 'credits') return 'credits';
  return 'all';
}

export function historyPageHref(
  page: number,
  kind: HistoryKindFilter = 'all',
  dates: HistoryDateRange = {},
): string {
  const qs = new URLSearchParams();
  if (page > 1) qs.set('page', String(page));
  if (kind !== 'all') qs.set('kind', kind);
  if (dates.from) qs.set('from', dates.from);
  if (dates.to) qs.set('to', dates.to);
  const query = qs.toString();
  return query ? `/billing/usage/history?${query}` : '/billing/usage/history';
}

export function localDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function parseDateKey(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw.trim());
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]);
  const d = Number(match[3]);
  const date = new Date(y, m - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) {
    return null;
  }
  return `${match[1]}-${match[2]}-${match[3]}`;
}

function dateFromKey(dateKey: string): Date | null {
  const parsed = parseDateKey(dateKey);
  if (!parsed) return null;
  const [y, m, d] = parsed.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function startOfLocalDayIso(dateKey: string): string | undefined {
  const date = dateFromKey(dateKey);
  return date ? date.toISOString() : undefined;
}

export function exclusiveEndOfLocalDayIso(dateKey: string): string | undefined {
  const date = dateFromKey(dateKey);
  if (!date) return undefined;
  date.setDate(date.getDate() + 1);
  return date.toISOString();
}

export function presetDateRange(
  preset: Exclude<HistoryDatePreset, 'custom'>,
  now = new Date(),
): HistoryDateRange {
  if (preset === 'all') return { from: null, to: null };
  const to = localDateKey(now);
  if (preset === 'today') return { from: to, to };
  const days = preset === '7d' ? 6 : 29;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - days);
  return { from: localDateKey(start), to };
}

export function matchDatePreset(
  dates: HistoryDateRange,
  now = new Date(),
): HistoryDatePreset {
  if (!dates.from && !dates.to) return 'all';
  for (const preset of ['today', '7d', '30d'] as const) {
    const expected = presetDateRange(preset, now);
    if (dates.from === expected.from && dates.to === expected.to) return preset;
  }
  return 'custom';
}

export function isKnownHistoryKind(
  kind: string,
): kind is Exclude<UsageHistoryKind, string> {
  return (
    isAiHistoryKind(kind) ||
    kind === 'credit_grant' ||
    kind === 'credit_consume' ||
    kind === 'credit_adjust' ||
    kind === 'credit_expire'
  );
}

export function historyKindLabelKey(kind: string): string {
  return isKnownHistoryKind(kind) ? `usage.kind.${kind}` : 'usage.kind.other';
}

export function creditDeltaSign(kind: string): 1 | -1 {
  if (kind === 'credit_consume' || kind === 'credit_expire') return -1;
  return 1;
}

export function historyDayKey(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function historyDayBucket(
  iso: string,
  now = new Date(),
): 'today' | 'yesterday' | 'other' {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'other';
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startTarget = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  );
  const diffDays = Math.round(
    (startToday.getTime() - startTarget.getTime()) / 86_400_000,
  );
  if (diffDays === 0) return 'today';
  if (diffDays === 1) return 'yesterday';
  return 'other';
}

export function groupHistoryByDay(
  items: UsageHistoryItem[],
): { key: string; items: UsageHistoryItem[] }[] {
  const groups: { key: string; items: UsageHistoryItem[] }[] = [];
  const index = new Map<string, UsageHistoryItem[]>();
  for (const item of items) {
    const key = historyDayKey(item.created_at);
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

export function operationLabelKey(operationType: string | null | undefined): string {
  if (
    operationType === 'chat' ||
    operationType === 'generation' ||
    operationType === 'generation_attempt' ||
    operationType === 'general_expert' ||
    operationType === 'general_fallback' ||
    operationType === 'pdf_parse' ||
    operationType === 'embedding' ||
    operationType === 'embed_query' ||
    operationType === 'rerank' ||
    operationType === 'title'
  ) {
    return `usage.operation.${operationType}`;
  }
  return 'usage.operation.other';
}

export function sourceLabelKey(sourceType: string | null | undefined): string {
  if (
    sourceType === 'ai_usage' ||
    sourceType === 'manual' ||
    sourceType === 'test'
  ) {
    return `usage.source.${sourceType}`;
  }
  return 'usage.source.other';
}

export function shortenId(id: string): string {
  const compact = id.replace(/-/g, '');
  if (compact.length <= 8) return id;
  return compact.slice(0, 8);
}
