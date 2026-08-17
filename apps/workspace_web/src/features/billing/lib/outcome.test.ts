import { describe, expect, it } from 'vitest';
import {
  billingContinuePath,
  paymentNoticeFromState,
  paymentNoticeFromStatus,
} from './outcome';

describe('payment outcome', () => {
  it('maps backend statuses to notices', () => {
    expect(paymentNoticeFromStatus('paid')).toBe('success');
    expect(paymentNoticeFromStatus('failed')).toBe('failed');
    expect(paymentNoticeFromStatus('cancelled')).toBe('failed');
    expect(paymentNoticeFromStatus('redirected')).toBe('pending');
  });

  it('sends subscriptions to the subscription page and packs to credits', () => {
    expect(billingContinuePath('subscription')).toBe('/billing/subscription');
    expect(billingContinuePath('credit_pack')).toBe('/billing/credits');
    expect(billingContinuePath('app_one_time')).toBe('/apps');
    expect(billingContinuePath('app_subscription')).toBe('/apps');
    expect(billingContinuePath(undefined)).toBe('/billing/subscription');
  });

  it('reads notice from router state', () => {
    expect(paymentNoticeFromState({ paymentNotice: 'failed' })).toBe('failed');
    expect(paymentNoticeFromState({ paymentNotice: 'nope' })).toBeNull();
    expect(paymentNoticeFromState(null)).toBeNull();
  });
});
