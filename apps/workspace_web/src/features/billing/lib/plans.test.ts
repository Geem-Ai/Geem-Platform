import { describe, expect, it } from 'vitest';
import type { PurchasablePlan } from '@/services/api/billing';
import { sortPlansForDisplay } from './plans';

function plan(id: string, name: string, price: string): PurchasablePlan {
  return {
    id,
    code: id,
    name,
    description: null,
    status: 'active',
    price_amount: price,
    currency: 'SAR',
    entitlements: [],
  };
}

describe('sortPlansForDisplay', () => {
  it('puts the current plan first then sorts by catalog price', () => {
    const ordered = sortPlansForDisplay(
      [plan('c', 'Growth', '199.00'), plan('a', 'Starter', '49.00'), plan('b', 'Team', '99.00')],
      'c',
    );
    expect(ordered.map((item) => item.id)).toEqual(['c', 'a', 'b']);
  });
});
