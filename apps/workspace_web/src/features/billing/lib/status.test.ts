import { describe, expect, it } from 'vitest';
import {
  purchaseKindLabelKey,
  purchaseStatusBadgeVariant,
  purchaseStatusLabelKey,
} from './status';

describe('purchase status presentation', () => {
  it('maps backend statuses to localized keys and badge variants', () => {
    expect(purchaseStatusLabelKey('paid')).toBe('billing.status.paid');
    expect(purchaseStatusLabelKey('redirected')).toBe('billing.status.redirected');
    expect(purchaseStatusLabelKey('clickpay-A')).toBe('billing.status.unknown');
    expect(purchaseStatusBadgeVariant('paid')).toBe('success');
    expect(purchaseStatusBadgeVariant('pending')).toBe('warning');
    expect(purchaseStatusBadgeVariant('failed')).toBe('destructive');
  });

  it('maps purchase kinds without provider names', () => {
    expect(purchaseKindLabelKey('subscription')).toBe('billing.kind.subscription');
    expect(purchaseKindLabelKey('credit_pack')).toBe('billing.kind.creditPack');
  });
});
