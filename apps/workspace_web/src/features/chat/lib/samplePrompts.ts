/** Static i18n keys for Saudi-market sample prompts (never LLM-generated). */
export const SAMPLE_PROMPT_KEYS = [
  'chat.samplePrompts.p01',
  'chat.samplePrompts.p02',
  'chat.samplePrompts.p03',
  'chat.samplePrompts.p04',
  'chat.samplePrompts.p05',
  'chat.samplePrompts.p06',
  'chat.samplePrompts.p07',
  'chat.samplePrompts.p08',
  'chat.samplePrompts.p09',
  'chat.samplePrompts.p10',
  'chat.samplePrompts.p11',
  'chat.samplePrompts.p12',
  'chat.samplePrompts.p13',
  'chat.samplePrompts.p14',
  'chat.samplePrompts.p15',
  'chat.samplePrompts.p16',
  'chat.samplePrompts.p17',
  'chat.samplePrompts.p18',
  'chat.samplePrompts.p19',
  'chat.samplePrompts.p20',
  'chat.samplePrompts.p21',
  'chat.samplePrompts.p22',
  'chat.samplePrompts.p23',
  'chat.samplePrompts.p24',
  'chat.samplePrompts.p25',
  'chat.samplePrompts.p26',
  'chat.samplePrompts.p27',
  'chat.samplePrompts.p28',
  'chat.samplePrompts.p29',
  'chat.samplePrompts.p30',
] as const;

export type SamplePromptKey = (typeof SAMPLE_PROMPT_KEYS)[number];

/** Fisher–Yates shuffle; returns `count` unique keys from the static pool. */
export function pickSamplePromptKeys(count = 5): SamplePromptKey[] {
  const n = Math.min(Math.max(0, count), SAMPLE_PROMPT_KEYS.length);
  const pool = [...SAMPLE_PROMPT_KEYS];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = pool[i]!;
    pool[i] = pool[j]!;
    pool[j] = tmp;
  }
  return pool.slice(0, n);
}
