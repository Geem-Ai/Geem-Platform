import type { BillingEntitlement } from '@/services/api/billing';
import type { EntitlementItem } from '@/services/api/usage';
import {
  formatBytesLabel,
  formatCount,
  isUnlimitedLimit,
  type ByteUnitKey,
} from '@/features/usage/lib/quota';

const KNOWN_KEYS = new Set([
  'ai_tokens_daily',
  'ai_tokens_weekly',
  'ai_tokens_monthly',
  'experts_limit',
  'storage_bytes',
  'api_requests_per_minute',
]);

/** Daily → weekly → monthly (alphabetical order would put monthly before weekly). */
export const ENTITLEMENT_DISPLAY_ORDER = [
  'ai_tokens_daily',
  'ai_tokens_weekly',
  'ai_tokens_monthly',
  'experts_limit',
  'storage_bytes',
  'api_requests_per_minute',
] as const;

export function sortEntitlements<T extends { key: string }>(items: readonly T[]): T[] {
  return [...items].sort((a, b) => {
    const ai = ENTITLEMENT_DISPLAY_ORDER.indexOf(
      a.key as (typeof ENTITLEMENT_DISPLAY_ORDER)[number],
    );
    const bi = ENTITLEMENT_DISPLAY_ORDER.indexOf(
      b.key as (typeof ENTITLEMENT_DISPLAY_ORDER)[number],
    );
    const ao = ai === -1 ? ENTITLEMENT_DISPLAY_ORDER.length : ai;
    const bo = bi === -1 ? ENTITLEMENT_DISPLAY_ORDER.length : bi;
    if (ao !== bo) return ao - bo;
    return a.key.localeCompare(b.key);
  });
}

export function entitlementLabelKey(key: string): string {
  if (KNOWN_KEYS.has(key)) return `billing.entitlements.${key}`;
  return 'billing.entitlements.other';
}

export function formatEntitlementValue(
  item: BillingEntitlement | EntitlementItem,
  locale: string,
  byteUnit: (unit: ByteUnitKey) => string,
): string {
  if (typeof item.value === 'boolean') {
    return item.value ? 'billing.entitlements.on' : 'billing.entitlements.off';
  }
  if (typeof item.value === 'number') {
    if (item.key === 'storage_bytes') {
      if (isUnlimitedLimit(item.value)) return 'billing.entitlements.unlimited';
      return formatBytesLabel(item.value, locale, byteUnit);
    }
    if (isUnlimitedLimit(item.value)) return 'billing.entitlements.unlimited';
    return formatCount(item.value, locale);
  }
  return String(item.value);
}

export function isEntitlementI18nValue(formatted: string): boolean {
  return formatted.startsWith('billing.entitlements.');
}
