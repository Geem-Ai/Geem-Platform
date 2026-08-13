import { describe, expect, it } from 'vitest';
import { internalReturnPath, safeInternalPath } from './guards';

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
