import { describe, expect, it } from 'vitest';
import {
  isClientAgentEnabled,
  parseRagConfig,
  serializeRagConfig,
} from './rag-config';

describe('Expert rag_config client agent settings', () => {
  it('reads a stored client_agent flag independently of retrieval knobs', () => {
    const raw = {
      top_k: 12,
      rerank_top_n: 4,
      similarity_threshold: 0.35,
      client_agent: { enabled: true },
    };

    expect(parseRagConfig(raw)).toEqual({
      top_k: 12,
      rerank_top_n: 4,
      similarity_threshold: 0.35,
    });
    expect(isClientAgentEnabled(raw)).toBe(true);
    expect(isClientAgentEnabled({ client_agent: { enabled: false } })).toBe(false);
  });

  it('preserves client_agent when serializing an ordinary Expert edit', () => {
    expect(
      serializeRagConfig(
        { top_k: 10, rerank_top_n: 5, similarity_threshold: 0.5 },
        true,
      ),
    ).toEqual({
      top_k: 10,
      rerank_top_n: 5,
      similarity_threshold: 0.5,
      client_agent: { enabled: true },
    });
  });
});
