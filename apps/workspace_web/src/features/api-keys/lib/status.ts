import type { ApiKey, ApiKeyStatus } from '@/services/api/api-keys';

export function apiKeyStatus(key: {
  revoked_at: string | null;
  expires_at: string | null;
  now?: Date;
}): ApiKeyStatus {
  if (key.revoked_at) return 'revoked';
  if (key.expires_at) {
    const expires = new Date(key.expires_at);
    const now = key.now ?? new Date();
    if (!Number.isNaN(expires.getTime()) && expires.getTime() <= now.getTime()) {
      return 'expired';
    }
  }
  return 'active';
}

export function maskedApiKey(key: Pick<ApiKey, 'prefix' | 'last_four'>): string {
  const prefix = key.prefix || 'geem_sk_';
  const last = key.last_four ? key.last_four : '';
  return last ? `${prefix}••••${last}` : `${prefix}••••••••`;
}

export function statusBadgeVariant(
  status: ApiKeyStatus,
): 'success' | 'secondary' | 'warning' {
  if (status === 'active') return 'success';
  if (status === 'expired') return 'warning';
  return 'secondary';
}
