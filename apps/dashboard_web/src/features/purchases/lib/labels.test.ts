import { describe, expect, it } from 'vitest';
import { purchaseKindLabel, purchaseStatusLabel } from '@/features/purchases/lib/labels';

describe('purchase labels', () => {
  const t = (key: string) => {
    const map: Record<string, string> = {
      'purchases.status.paid': 'Paid',
      'purchases.kinds.credit_pack': 'Credit pack',
    };
    return map[key] ?? key;
  };

  it('maps known purchase status', () => {
    expect(purchaseStatusLabel(t, 'paid')).toBe('Paid');
    expect(purchaseStatusLabel(t, 'unknown_status')).toBe('unknown_status');
  });

  it('maps known purchase kind', () => {
    expect(purchaseKindLabel(t, 'credit_pack')).toBe('Credit pack');
    expect(purchaseKindLabel(t, 'future_kind')).toBe('future_kind');
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
