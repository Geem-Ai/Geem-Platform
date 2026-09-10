import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  applyDocumentLocale,
  getStoredLocale,
} from '@/lib/i18n';

describe('document locale direction', () => {
  it('defaults to English when nothing is stored', () => {
    localStorage.removeItem(LOCALE_STORAGE_KEY);
    expect(DEFAULT_LOCALE).toBe('en');
    expect(getStoredLocale()).toBe('en');
  });

  it('applies LTR for English and RTL for Arabic', () => {
    applyDocumentLocale('en');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(getStoredLocale()).toBe('en');

    applyDocumentLocale('ar');
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
    expect(getStoredLocale()).toBe('ar');
  });
});
