import { describe, expect, it } from 'vitest';
import i18n, { applyDocumentLocale } from '@/lib/i18n';

describe('i18n + RTL', () => {
  it('sets English LTR', async () => {
    await i18n.changeLanguage('en');
    expect(i18n.t('app.name')).toBe('Geem');
    expect(i18n.t('app.product')).toBe('Geem Admin');
    expect(document.documentElement.lang).toBe('en');
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('sets Arabic RTL', async () => {
    await i18n.changeLanguage('ar');
    expect(i18n.t('app.name')).toBe('Geem');
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
    applyDocumentLocale('ar');
    expect(document.documentElement.dir).toBe('rtl');
  });
});
