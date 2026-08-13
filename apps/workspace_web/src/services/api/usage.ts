import { apiRequest } from './client';

export type Meter = {
  limit: number;
  used: number;
  reserved: number;
  remaining: number;
  period_start: string | null;
  period_end: string | null;
};

export type StorageUsage = {
  limit_bytes: number;
  used_bytes: number;
  remaining_bytes: number;
  reserved_bytes: number;
  percentage: number;
};

export type UsageSummary = {
  ai_tokens: {
    daily: Meter;
    weekly: Meter;
    monthly: Meter;
  };
  ai: {
    daily: Meter;
    weekly: Meter;
    monthly: Meter;
  };
  experts: Meter;
  storage_bytes: Meter;
  storage: StorageUsage;
  credits: {
    balance: number;
  };
};

export type UsageHistoryKind =
  | 'ai_tokens'
  | 'chat_tokens'
  | 'embed_tokens'
  | 'rerank_tokens'
  | 'ocr_tokens'
  | 'title_tokens'
  | 'credit_grant'
  | 'credit_consume'
  | 'credit_adjust'
  | 'credit_expire'
  | string;

export const AI_HISTORY_KINDS = new Set<string>([
  'ai_tokens',
  'chat_tokens',
  'embed_tokens',
  'rerank_tokens',
  'ocr_tokens',
  'title_tokens',
]);

export function isAiHistoryKind(kind: string): boolean {
  return AI_HISTORY_KINDS.has(kind);
}

export type UsageHistoryItem = {
  id: string;
  kind: UsageHistoryKind;
  tokens: number | null;
  credits: number | null;
  created_at: string;
  operation_type?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  request_id?: string | null;
  source_type?: string | null;
};

export const USAGE_HISTORY_PREVIEW_LIMIT = 10;
export const USAGE_HISTORY_PAGE_SIZE = 25;

export type UsageHistoryCounts = {
  all: number;
  ai: number;
  credits: number;
};

export type UsageHistoryTokens = {
  input: number;
  output: number;
  total: number;
};

export type UsageHistory = {
  items: UsageHistoryItem[];
  total: number;
  limit: number;
  offset: number;
  counts?: UsageHistoryCounts;
  tokens?: UsageHistoryTokens;
};

export type Subscription = {
  id: string;
  status: string;
  plan: {
    id: string;
    code: string;
    name: string;
    status: string;
  };
  starts_at: string;
  current_period_start: string;
  current_period_end: string;
  ends_at: string | null;
};

export function getUsageSummary(): Promise<UsageSummary> {
  return apiRequest<UsageSummary>('/api/usage/summary');
}

export function getUsageHistory(params?: {
  limit?: number;
  offset?: number;
  kind?: string;
  from?: string;
  to?: string;
}): Promise<UsageHistory> {
  const qs = new URLSearchParams();
  qs.set('limit', String(params?.limit ?? USAGE_HISTORY_PREVIEW_LIMIT));
  qs.set('offset', String(params?.offset ?? 0));
  if (params?.kind && params.kind !== 'all') qs.set('kind', params.kind);
  if (params?.from) qs.set('from', params.from);
  if (params?.to) qs.set('to', params.to);
  return apiRequest<UsageHistory>(`/api/usage/history?${qs.toString()}`);
}

export function getSubscription(): Promise<Subscription> {
  return apiRequest<Subscription>('/api/subscription');
}
