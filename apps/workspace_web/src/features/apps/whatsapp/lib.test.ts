import { describe, expect, it } from 'vitest';
import { isConnectingStatus, isReadyStatus, resolveWhatsAppUiStatus, whatsappPhoneLabel } from './lib';

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

  it('maps disconnected Geem status to disconnected even if provider_status is empty', () => {
    expect(
      resolveWhatsAppUiStatus({ status: 'disconnected', provider_status: null }),
    ).toEqual({ key: 'disconnected', variant: 'secondary' });
  });

  it('prefers provider linking states over Geem row status', () => {
    expect(
      resolveWhatsAppUiStatus({ status: 'disconnected', provider_status: 'qr_ready' }),
    ).toEqual({ key: 'waitingForQr', variant: 'warning' });
    expect(
      resolveWhatsAppUiStatus({ status: 'active', provider_status: 'ready' }),
    ).toEqual({ key: 'connected', variant: 'success' });
  });
});

describe('whatsappPhoneLabel', () => {
  it('formats phone and falls back to external_account_id', () => {
    expect(
      whatsappPhoneLabel({ phone: '966500000000', external_account_id: null }),
    ).toBe('+966500000000');
    expect(
      whatsappPhoneLabel({ phone: null, external_account_id: '966511111111' }),
    ).toBe('+966511111111');
    expect(
      whatsappPhoneLabel({ phone: null, external_account_id: 'not-a-phone' }),
    ).toBeNull();
  });
});
