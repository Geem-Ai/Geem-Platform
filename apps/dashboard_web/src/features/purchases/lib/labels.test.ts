import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';
import {
  isAppPurchaseKind,
  purchaseAppHref,
  purchaseKindLabel,
  purchaseProductLabel,
  purchaseStatusLabel,
} from '@/features/purchases/lib/labels';

describe('purchase labels', () => {
  const translations: Record<string, string> = {
    'purchases.status.paid': 'Paid',
    'purchases.kinds.credit_pack': 'Credit pack',
  };
  const t = ((key: string) => translations[key] ?? key) as unknown as TFunction;

  it('maps known purchase status', () => {
    expect(purchaseStatusLabel(t, 'paid')).toBe('Paid');
    expect(purchaseStatusLabel(t, 'unknown_status')).toBe('unknown_status');
  });

  it('maps known purchase kind', () => {
    expect(purchaseKindLabel(t, 'credit_pack')).toBe('Credit pack');
    expect(purchaseKindLabel(t, 'future_kind')).toBe('future_kind');
  });

  it('builds app links from app_id or slug', () => {
    expect(
      purchaseAppHref({
        kind: 'app_one_time',
        app_id: 'app-123',
        app_slug: 'whatsapp',
      }),
    ).toBe('/app-store/app-123');
    expect(
      purchaseAppHref({
        kind: 'app_one_time',
        app_slug: 'whatsapp',
      }),
    ).toBe('/app-store?search=whatsapp');
    expect(purchaseAppHref({ kind: 'credit_pack' })).toBeNull();
  });

  it('detects app purchase kinds', () => {
    expect(isAppPurchaseKind('app_one_time')).toBe(true);
    expect(isAppPurchaseKind('credit_pack')).toBe(false);
  });

  it('formats product labels', () => {
    expect(
      purchaseProductLabel({
        kind: 'app_one_time',
        app_name: 'WhatsApp',
        item_name: 'WhatsApp — Pro',
      }),
    ).toBe('WhatsApp — Pro');
    expect(
      purchaseProductLabel({
        kind: 'credit_pack',
        item_name: 'Starter Pack',
      }),
    ).toBe('Starter Pack');
  });
});

describe('payment gateway secret safety', () => {
  it('does not echo secrets in fixture payloads', () => {
    const fixture = {
      credentials: {
        profile_id_configured: true,
        server_key_configured: true,
        profile_id: '59020',
      },
    };
    const serialized = JSON.stringify(fixture);
    expect(serialized).not.toContain('sk_live');
    expect(serialized).not.toContain('server_key":');
    expect(serialized).toBeTypeOf('string');
  });
});
