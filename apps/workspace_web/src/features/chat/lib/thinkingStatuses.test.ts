import { describe, expect, it, vi } from 'vitest';
import {
  THINKING_STATUS_KEYS,
  shuffleThinkingStatusKeys,
} from './thinkingStatuses';

describe('thinkingStatuses', () => {
  it('exports a non-empty static key pool', () => {
    expect(THINKING_STATUS_KEYS.length).toBeGreaterThanOrEqual(4);
    expect(THINKING_STATUS_KEYS.every((k) => k.startsWith('chat.thinkingStatuses.'))).toBe(
      true,
    );
  });

  it('shuffles all keys without dropping any', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.42);
    const shuffled = shuffleThinkingStatusKeys();
    expect(shuffled).toHaveLength(THINKING_STATUS_KEYS.length);
    expect(new Set(shuffled)).toEqual(new Set(THINKING_STATUS_KEYS));
    vi.restoreAllMocks();
  });
});
