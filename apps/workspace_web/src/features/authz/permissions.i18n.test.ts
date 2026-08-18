import { describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import {
  ALL_PERMISSION_KEYS,
  permissionDescriptionKey,
  permissionLabelKey,
} from './permissions';

describe('permission UX copy', () => {
  it('has a readable name and description for every key in en and ar', async () => {
    for (const locale of ['en', 'ar'] as const) {
      await i18n.changeLanguage(locale);
      for (const key of ALL_PERMISSION_KEYS) {
        const name = i18n.t(permissionLabelKey(key));
        const description = i18n.t(permissionDescriptionKey(key));
        expect(name, `${locale} ${key} name`).not.toBe(permissionLabelKey(key));
        expect(name).not.toBe(key);
        expect(name.length).toBeGreaterThan(0);
        expect(description, `${locale} ${key} description`).not.toBe(
          permissionDescriptionKey(key),
        );
        expect(description.length).toBeGreaterThan(0);
      }
    }
    await i18n.changeLanguage('en');
  });
});
