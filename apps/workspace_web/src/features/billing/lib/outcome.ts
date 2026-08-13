import { isFailedStatus, isPaidStatus } from './status';

export type PaymentNotice = 'success' | 'failed' | 'pending';

export const PAYMENT_NOTICE_STATE_KEY = 'paymentNotice';

export function paymentNoticeFromStatus(status: string): PaymentNotice {
  if (isPaidStatus(status)) return 'success';
  if (isFailedStatus(status)) return 'failed';
  return 'pending';
}

export function billingContinuePath(kind: string | undefined): string {
  return kind === 'credit_pack' ? '/billing/credits' : '/billing/subscription';
}

export function paymentNoticeFromState(state: unknown): PaymentNotice | null {
  if (!state || typeof state !== 'object') return null;
  const value = (state as { [PAYMENT_NOTICE_STATE_KEY]?: unknown })[PAYMENT_NOTICE_STATE_KEY];
  if (value === 'success' || value === 'failed' || value === 'pending') return value;
  return null;
}
