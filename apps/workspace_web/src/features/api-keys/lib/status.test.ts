import { describe, expect, it } from 'vitest';
import { apiKeyStatus, maskedApiKey } from './status';

describe('apiKeyStatus', () => {
  const now = new Date('2026-08-13T12:00:00Z');

  it('marks revoked first', () => {
    expect(
      apiKeyStatus({
        revoked_at: '2026-08-01T00:00:00Z',
        expires_at: '2026-09-01T00:00:00Z',
        now,
      }),
    ).toBe('revoked');
  });

  it('marks expired when past expires_at', () => {
    expect(
      apiKeyStatus({
        revoked_at: null,
        expires_at: '2026-08-01T00:00:00Z',
        now,
      }),
    ).toBe('expired');
  });

  it('marks active otherwise', () => {
    expect(
      apiKeyStatus({
        revoked_at: null,
        expires_at: null,
        now,
      }),
    ).toBe('active');
  });
});

describe('maskedApiKey', () => {
  it('uses backend prefix and last four only', () => {
    expect(maskedApiKey({ prefix: 'geem_sk_abcd1234', last_four: 'wxyz' })).toBe(
      'geem_sk_abcd1234••••wxyz',
    );
  });
});
