import { describe, expect, it } from 'vitest';
import { sanitizeCitationSnippet } from './sanitizeCitationSnippet';

describe('sanitizeCitationSnippet', () => {
  it('returns empty string for nullish or blank input', () => {
    expect(sanitizeCitationSnippet(null)).toBe('');
    expect(sanitizeCitationSnippet(undefined)).toBe('');
    expect(sanitizeCitationSnippet('   ')).toBe('');
  });

  it('strips markdown image placeholders mixed with Arabic text', () => {
    const raw =
      'تطبيق خاص مبيعات ![img-0.jpeg](img-0.jpeg) إدارة مطبخ ![img-1.jpeg](img-1.jpeg) فواتير إلكترونية';
    expect(sanitizeCitationSnippet(raw)).toBe(
      'تطبيق خاص مبيعات إدارة مطبخ فواتير إلكترونية',
    );
  });

  it('strips empty-alt markdown images', () => {
    expect(sanitizeCitationSnippet('Before ![](x.png) after')).toBe(
      'Before after',
    );
  });

  it('strips HTML img tags', () => {
    expect(
      sanitizeCitationSnippet('Hello <img src="a.jpg" alt="x" /> world'),
    ).toBe('Hello world');
  });

  it('collapses excessive whitespace and newlines', () => {
    expect(sanitizeCitationSnippet('a   \n\n  b')).toBe('a b');
  });

  it('returns empty when only image markup remains', () => {
    expect(sanitizeCitationSnippet('![img-0.jpeg](img-0.jpeg)')).toBe('');
  });

  it('preserves clean snippets unchanged', () => {
    expect(
      sanitizeCitationSnippet('نظام السعد لإدارة المطاعم والمقاهي DAR ALSAAED'),
    ).toBe('نظام السعد لإدارة المطاعم والمقاهي DAR ALSAAED');
  });
});
