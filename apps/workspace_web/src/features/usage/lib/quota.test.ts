import { describe, expect, it } from 'vitest';
import {
  formatBytesLabel,
  formatBytesParts,
  isUnlimitedLimit,
  meterPercentage,
  quotaWarningLevel,
  worstWarningLevel,
} from './quota';

describe('quota warning levels', () => {
  it('is normal below 80%', () => {
    expect(quotaWarningLevel(79, 100, 21)).toBe('normal');
  });

  it('is approaching at 80%', () => {
    expect(quotaWarningLevel(80, 100, 20)).toBe('approaching');
  });

  it('is critical at 95%', () => {
    expect(quotaWarningLevel(95, 100, 5)).toBe('critical');
  });

  it('is exhausted at 100% or remaining 0', () => {
    expect(quotaWarningLevel(100, 100, 0)).toBe('exhausted');
    expect(quotaWarningLevel(50, 100, 0)).toBe('exhausted');
  });

  it('treats zero limit as exhausted (no allowance)', () => {
    expect(quotaWarningLevel(0, 0, 0)).toBe('exhausted');
    expect(meterPercentage(0, 0)).toBe(100);
  });

  it('treats negative limit as unlimited', () => {
    expect(isUnlimitedLimit(-1)).toBe(true);
    expect(quotaWarningLevel(999, -1, 999)).toBe('normal');
    expect(meterPercentage(999, -1)).toBe(0);
  });

  it('counts reserved tokens toward percentage and warning level', () => {
    expect(meterPercentage(50, 100, 30)).toBe(80);
    expect(quotaWarningLevel(50, 100, 20, 30)).toBe('approaching');
  });

  it('picks the worst warning level in a set', () => {
    expect(worstWarningLevel(['normal', 'approaching', 'critical'])).toBe(
      'critical',
    );
    expect(worstWarningLevel(['normal'])).toBe('normal');
  });
});

describe('byte formatting', () => {
  const enUnit = (unit: 'bytes' | 'kb' | 'mb' | 'gb' | 'tb') =>
    ({ bytes: 'B', kb: 'KB', mb: 'MB', gb: 'GB', tb: 'TB' })[unit];
  const arUnit = (unit: 'bytes' | 'kb' | 'mb' | 'gb' | 'tb') =>
    ({
      bytes: 'بايت',
      kb: 'كيلوبايت',
      mb: 'ميغابايت',
      gb: 'غيغابايت',
      tb: 'تيرابايت',
    })[unit];

  it('formats exact bytes human-readably with localized units', () => {
    expect(formatBytesParts(512)).toEqual({ value: 512, unit: 'bytes' });
    expect(formatBytesLabel(1536, 'en', enUnit)).toContain('KB');
    expect(formatBytesLabel(1048576, 'en', enUnit)).toContain('MB');
    expect(formatBytesLabel(1048576, 'ar', arUnit)).toContain('ميغابايت');
  });
});
