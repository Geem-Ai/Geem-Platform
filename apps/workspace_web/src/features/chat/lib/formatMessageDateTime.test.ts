import { describe, expect, it } from 'vitest';
import {
  formatMessageDateTime,
  formatMessageDateTimeExact,
} from './formatMessageDateTime';

describe('formatMessageDateTime', () => {
  it('returns empty string for invalid dates', () => {
    expect(formatMessageDateTime('not-a-date', 'en')).toBe('');
  });

  it('formats today with time only', () => {
    const now = new Date();
    const iso = now.toISOString();
    const formatted = formatMessageDateTime(iso, 'en');
    expect(formatted.length).toBeGreaterThan(0);
    // Should not include a year for same-day messages.
    expect(formatted).not.toMatch(/202\d/);
  });

  it('formats older dates with date and time', () => {
    const formatted = formatMessageDateTime('2024-01-15T10:30:00.000Z', 'en');
    expect(formatted).toMatch(/15/);
    expect(formatted.length).toBeGreaterThan(4);
  });
});

describe('formatMessageDateTimeExact', () => {
  it('returns Y-m-d H:i:s in local time', () => {
    const date = new Date(2024, 0, 15, 9, 8, 7); // local components
    expect(formatMessageDateTimeExact(date.toISOString())).toBe(
      '2024-01-15 09:08:07',
    );
  });

  it('returns empty string for invalid dates', () => {
    expect(formatMessageDateTimeExact('nope')).toBe('');
  });
});
