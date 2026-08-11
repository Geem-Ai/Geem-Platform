import { describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import { isGeemGeneralExpert, localizeExpertDisplay } from './localize';

describe('localizeExpertDisplay', () => {
  it('detects Geem General by knowledge_mode', () => {
    expect(
      isGeemGeneralExpert({ knowledge_mode: 'general', ownership: 'platform' }),
    ).toBe(true);
    expect(isGeemGeneralExpert({ knowledge_mode: 'rag', ownership: 'platform' })).toBe(
      false,
    );
  });

  it('localizes Geem General in English and Arabic', async () => {
    const expert = {
      name: 'Geem General Assistant',
      description: 'API desc',
      knowledge_mode: 'general' as const,
      ownership: 'platform' as const,
    };

    await i18n.changeLanguage('en');
    expect(localizeExpertDisplay(expert, i18n.t.bind(i18n)).name).toBe(
      'Geem General Assistant',
    );

    await i18n.changeLanguage('ar');
    const ar = localizeExpertDisplay(expert, i18n.t.bind(i18n));
    expect(ar.name).toBe('خبير Geem العام');
    expect(ar.description).toContain('Geem');
  });

  it('passes through workspace Experts unchanged', async () => {
    await i18n.changeLanguage('ar');
    const expert = {
      name: 'Legal',
      description: 'Law',
      knowledge_mode: 'rag' as const,
      ownership: 'workspace' as const,
    };
    expect(localizeExpertDisplay(expert, i18n.t.bind(i18n))).toEqual({
      name: 'Legal',
      description: 'Law',
    });
  });
});
