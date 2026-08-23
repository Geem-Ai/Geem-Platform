import { describe, expect, it } from 'vitest';
import { clampRagValue, parseRagConfig, serializeRagConfig } from './rag-config';

describe('rag-config', () => {
  it('parses defaults when empty', () => {
    const parsed = parseRagConfig(null);
    expect(parsed.top_k).toBe(10);
    expect(parsed.rerank_top_n).toBe(5);
  });

  it('serializes supported knobs only', () => {
    const payload = serializeRagConfig({
      top_k: 12,
      rerank_top_n: 4,
      similarity_threshold: 0.42,
    });
    expect(payload).toEqual({
      top_k: 12,
      rerank_top_n: 4,
      similarity_threshold: 0.42,
    });
  });

  it('clamps values to bounds', () => {
    expect(clampRagValue('top_k', 999)).toBe(100);
    expect(clampRagValue('similarity_threshold', -1)).toBe(0);
  });
});
