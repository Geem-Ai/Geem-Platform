import { afterEach, describe, expect, it } from 'vitest';
import {
  consumePaymentReturn,
  continueAfterAuth,
  internalReturnPath,
  rememberPaymentReturn,
  safeInternalPath,
} from './guards';

describe('internalReturnPath', () => {
  it('keeps payment result query parameters for post-login return', () => {
    expect(
      internalReturnPath({
        pathname: '/billing/payment/success',
        search: '?purchase=pur-1',
      }),
    ).toBe('/billing/payment/success?purchase=pur-1');
  });
});

describe('safeInternalPath', () => {
  it('accepts relative paths and rejects protocol-relative URLs', () => {
    expect(safeInternalPath('/billing/payment/success?purchase=pur-1')).toBe(
      '/billing/payment/success?purchase=pur-1',
    );
    expect(safeInternalPath('//evil.example/phish')).toBeNull();
    expect(safeInternalPath('https://evil.example')).toBeNull();
  });
});

describe('continueAfterAuth', () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it('returns the explicit from path instead of home/chat', () => {
    expect(continueAfterAuth('/billing/payment/success?purchase=pur-1')).toBe(
      '/billing/payment/success?purchase=pur-1',
    );
  });

  it('ignores login/onboarding from values', () => {
    expect(continueAfterAuth('/login')).toBe('/');
    expect(continueAfterAuth('/onboarding')).toBe('/');
  });

  it('returns the invitation accept path including the query', () => {
    expect(continueAfterAuth('/invitations/accept?token=abc')).toBe(
      '/invitations/accept?token=abc',
    );
  });

  it('restores a stashed ClickPay return when from is missing', () => {
    rememberPaymentReturn({
      pathname: '/billing/payment/success',
      search: '?purchase=pur-1',
    });
    expect(continueAfterAuth(undefined)).toBe(
      '/billing/payment/success?purchase=pur-1',
    );
    expect(consumePaymentReturn()).toBeNull();
  });
});
