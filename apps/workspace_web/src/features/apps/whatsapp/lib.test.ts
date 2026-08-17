import { describe, expect, it } from 'vitest';
import { isConnectingStatus, isReadyStatus } from './lib';

describe('WhatsApp status helpers', () => {
  it('does not treat ACTIVE + qr_ready as ready (reconnect QR)', () => {
    expect(
      isReadyStatus({ status: 'active', provider_status: 'qr_ready' }),
    ).toBe(false);
    expect(
      isConnectingStatus({ status: 'active', provider_status: 'qr_ready' }),
    ).toBe(true);
  });

  it('treats provider ready as ready', () => {
    expect(
      isReadyStatus({ status: 'connecting', provider_status: 'ready' }),
    ).toBe(true);
    expect(
      isReadyStatus({ status: 'active', provider_status: 'ready' }),
    ).toBe(true);
  });

  it('treats active without provider status as ready', () => {
    expect(isReadyStatus({ status: 'active', provider_status: null })).toBe(
      true,
    );
  });
});
