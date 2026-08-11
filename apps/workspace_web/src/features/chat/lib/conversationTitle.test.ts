import { describe, expect, it } from 'vitest';
import {
  isUsableConversationTitle,
  provisionalConversationTitle,
} from './conversationTitle';

describe('provisionalConversationTitle', () => {
  it('returns trimmed short titles unchanged', () => {
    expect(provisionalConversationTitle('  Hello laws  ')).toBe('Hello laws');
  });

  it('truncates long titles on a word boundary', () => {
    const long =
      'What is the maximum probation period under Saudi Labor Law and related exceptions for contracts';
    const titled = provisionalConversationTitle(long, 40);
    expect(titled.endsWith('…')).toBe(true);
    expect(titled.length).toBeLessThanOrEqual(41);
  });
});

describe('isUsableConversationTitle', () => {
  it('rejects instruction-echo junk like Language:', () => {
    expect(isUsableConversationTitle('Language:')).toBe(false);
    expect(isUsableConversationTitle('Language')).toBe(false);
    expect(isUsableConversationTitle('اللغة:')).toBe(false);
    expect(isUsableConversationTitle('Title')).toBe(false);
  });

  it('accepts real topic titles', () => {
    expect(isUsableConversationTitle('أساسيات السجل التجاري')).toBe(true);
    expect(isUsableConversationTitle('Commercial register basics')).toBe(true);
  });
});
