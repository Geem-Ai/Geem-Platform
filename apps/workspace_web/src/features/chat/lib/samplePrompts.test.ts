import { describe, expect, it } from 'vitest';
import {
  SAMPLE_PROMPT_KEYS,
  pickSamplePromptKeys,
} from './samplePrompts';

describe('pickSamplePromptKeys', () => {
  it('returns the requested count of unique keys from the static pool', () => {
    const picked = pickSamplePromptKeys(5);
    expect(picked).toHaveLength(5);
    expect(new Set(picked).size).toBe(5);
    for (const key of picked) {
      expect(SAMPLE_PROMPT_KEYS).toContain(key);
    }
  });

  it('never exceeds the pool size', () => {
    const picked = pickSamplePromptKeys(100);
    expect(picked).toHaveLength(SAMPLE_PROMPT_KEYS.length);
    expect(new Set(picked).size).toBe(SAMPLE_PROMPT_KEYS.length);
  });

  it('exposes a static pool of 30 Saudi-market prompt keys', () => {
    expect(SAMPLE_PROMPT_KEYS).toHaveLength(30);
  });
});
