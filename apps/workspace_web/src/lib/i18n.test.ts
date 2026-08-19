import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  applyDocumentLocale,
  getStoredLocale,
} from '@/lib/i18n';

describe('document locale direction', () => {
  it('defaults to Arabic when nothing is stored', () => {
    localStorage.removeItem(LOCALE_STORAGE_KEY);
    expect(DEFAULT_LOCALE).toBe('ar');
    expect(getStoredLocale()).toBe('ar');
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
