/** Static i18n keys for AI reply loading status (typewriter cycle). */
export const THINKING_STATUS_KEYS = [
  'chat.thinkingStatuses.thinking',
  'chat.thinkingStatuses.checkingSources',
  'chat.thinkingStatuses.gatheringContext',
  'chat.thinkingStatuses.readingKnowledge',
  'chat.thinkingStatuses.preparingAnswer',
  'chat.thinkingStatuses.lookingUp',
] as const;

export type ThinkingStatusKey = (typeof THINKING_STATUS_KEYS)[number];

/** Fisher–Yates shuffle; returns all keys in a random order for a mixed cycle. */
export function shuffleThinkingStatusKeys(
  keys: readonly ThinkingStatusKey[] = THINKING_STATUS_KEYS,
): ThinkingStatusKey[] {
  const pool = [...keys];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = pool[i]!;
    pool[i] = pool[j]!;
    pool[j] = tmp;
  }
  return pool;
}
