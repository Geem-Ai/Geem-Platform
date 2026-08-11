import { describe, expect, it } from 'vitest';
import { applyDocumentLocale, getStoredLocale } from '@/lib/i18n';

describe('document locale direction', () => {
  it('applies LTR for English and RTL for Arabic', () => {
    applyDocumentLocale('en');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(getStoredLocale()).toBe('en');

    applyDocumentLocale('ar');
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
    expect(getStoredLocale()).toBe('ar');

    applyDocumentLocale('en');
  });
});
