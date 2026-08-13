import { describe, expect, it } from 'vitest';
import { apiUsageHref, parseApiUsagePage, parseApiUsagePeriod } from './period';

describe('api usage period helpers', () => {
  it('defaults unknown periods to 30d', () => {
    expect(parseApiUsagePeriod(null)).toBe('30d');
    expect(parseApiUsagePeriod('7d')).toBe('7d');
    expect(parseApiUsagePeriod('nope')).toBe('30d');
  });

  it('parses pages as positive integers', () => {
    expect(parseApiUsagePage(null)).toBe(1);
    expect(parseApiUsagePage('0')).toBe(1);
    expect(parseApiUsagePage('3.9')).toBe(3);
  });

  it('omits default page and empty key from the href', () => {
    expect(apiUsageHref('24h', null, 1)).toBe('/api/usage?period=24h');
    expect(apiUsageHref('7d', 'key-1', 2)).toBe(
      '/api/usage?period=7d&key=key-1&page=2',
    );
  });
});
