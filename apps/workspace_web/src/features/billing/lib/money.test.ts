import { describe, expect, it } from 'vitest';
import { compareMoneyAmount, formatMoney } from './money';

describe('formatMoney', () => {
  it('formats server-provided SAR amounts without arithmetic', () => {
    expect(formatMoney('99.00', 'SAR')).toBe('SAR 99.00');
    expect(formatMoney('15.50', 'sar')).toBe('SAR 15.50');
  });
});

describe('compareMoneyAmount', () => {
  it('orders catalog amounts numerically', () => {
    expect(compareMoneyAmount('9.00', '12.00')).toBeLessThan(0);
    expect(compareMoneyAmount('99.00', '9.00')).toBeGreaterThan(0);
  });
});
