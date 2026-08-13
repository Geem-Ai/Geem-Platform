import { apiRequest } from './client';

export const API_KEY_SCOPE_CHAT_WRITE = 'chat:write';

export type ApiKeyStatus = 'active' | 'revoked' | 'expired';

/** Safe list/detail DTO. Never includes the plaintext secret or hash. */
export type ApiKey = {
  id: string;
  workspace_id: string;
  name: string;
  prefix: string;
  last_four: string;
  scopes: string[];
  created_by: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string;
};

/** Create response only. Do not store this type in list query cache. */
export type CreatedApiKey = ApiKey & {
  key: string;
};

export type CreateApiKeyInput = {
  name: string;
  scopes?: string[];
  expires_at?: string | null;
};

export type ApiUsagePeriodKey = '24h' | '7d' | '30d';

export type ApiUsageMeter = {
  limit: number;
  used: number;
  reserved: number;
  remaining: number;
  period_start: string | null;
  period_end: string | null;
};

export type ApiUsageKeyRow = {
  api_key_id: string;
  name: string;
  prefix: string;
  last_four: string;
  billed_tokens: number;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type ApiUsageSummary = {
  rate_limit: {
    requests_per_minute: number;
  };
  ai_tokens: {
    billed: number;
  };
  workspace_ai_monthly: ApiUsageMeter;
  period: {
    key: ApiUsagePeriodKey;
    from_at: string;
    to_at: string;
  };
  keys: ApiUsageKeyRow[];
};

export type ApiUsageHistoryItem = {
  id: string;
  created_at: string;
  api_key_id: string;
  api_key_name: string | null;
  prefix: string | null;
  last_four: string | null;
  expert_id: string | null;
  family: string;
  model: string | null;
  billed_tokens: number;
  operation_type: string | null;
};

export type ApiUsageHistory = {
  items: ApiUsageHistoryItem[];
  total: number;
  limit: number;
  offset: number;
  period: ApiUsageSummary['period'];
};

export const API_USAGE_HISTORY_PAGE_SIZE = 25;

export function listApiKeys(): Promise<ApiKey[]> {
  return apiRequest<ApiKey[]>('/api/api-keys');
}

export function createApiKey(input: CreateApiKeyInput): Promise<CreatedApiKey> {
  return apiRequest<CreatedApiKey>('/api/api-keys', {
    method: 'POST',
    json: {
      name: input.name,
      scopes: input.scopes ?? [API_KEY_SCOPE_CHAT_WRITE],
      ...(input.expires_at ? { expires_at: input.expires_at } : {}),
    },
  });
}

export function revokeApiKey(apiKeyId: string): Promise<ApiKey> {
  return apiRequest<ApiKey>(`/api/api-keys/${apiKeyId}/revoke`, {
    method: 'POST',
  });
}

export function getApiUsageSummary(
  period: ApiUsagePeriodKey = '30d',
): Promise<ApiUsageSummary> {
  const qs = new URLSearchParams({ period });
  return apiRequest<ApiUsageSummary>(`/api/api-usage/summary?${qs.toString()}`);
}

export function getApiUsageHistory(params?: {
  limit?: number;
  offset?: number;
  period?: ApiUsagePeriodKey;
  api_key_id?: string;
}): Promise<ApiUsageHistory> {
  const qs = new URLSearchParams();
  qs.set('limit', String(params?.limit ?? API_USAGE_HISTORY_PAGE_SIZE));
  qs.set('offset', String(params?.offset ?? 0));
  qs.set('period', params?.period ?? '30d');
  if (params?.api_key_id) qs.set('api_key_id', params.api_key_id);
  return apiRequest<ApiUsageHistory>(`/api/api-usage/history?${qs.toString()}`);
}
