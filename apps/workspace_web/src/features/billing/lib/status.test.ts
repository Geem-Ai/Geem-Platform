import { describe, expect, it } from 'vitest';
import {
  formatPurchaseHistoryTitle,
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
    expect(purchaseKindLabelKey('app_one_time')).toBe('billing.kind.appOneTime');
    expect(purchaseKindLabelKey('app_subscription')).toBe('billing.kind.appSubscription');
    expect(purchaseKindLabelKey('app_subscription_renewal')).toBe('billing.kind.appRenewal');
  });

  it('formats App purchase history titles with app name', () => {
    const t = (key: string, opts?: Record<string, unknown>) =>
      key === 'billing.kind.appSubscriptionNamed'
        ? `${opts?.app} — New subscription`
        : key === 'billing.kind.appRenewalNamed'
          ? `${opts?.app} — Subscription renewal`
          : key === 'billing.kind.appOneTimeNamed'
            ? `${opts?.app} — One-time purchase`
            : key;
    expect(
      formatPurchaseHistoryTitle(
        { kind: 'app_subscription', app_name: 'WhatsApp', item_name: 'WhatsApp — Desk' },
        t,
      ),
    ).toBe('WhatsApp — New subscription');
    expect(
      formatPurchaseHistoryTitle(
        { kind: 'app_subscription_renewal', app_name: 'WhatsApp' },
        t,
      ),
    ).toBe('WhatsApp — Subscription renewal');
  });
});
