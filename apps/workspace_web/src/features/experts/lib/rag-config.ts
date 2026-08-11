import type { ExpertRagConfig } from '@/services/api/types';

export const RAG_CONFIG_DEFAULTS = {
  top_k: 10,
  rerank_top_n: 5,
  similarity_threshold: 0.5,
};

export const RAG_CONFIG_BOUNDS = {
  top_k: { min: 1, max: 100 },
  rerank_top_n: { min: 1, max: 50 },
  similarity_threshold: { min: 0, max: 1, step: 0.01 },
};

export function parseRagConfig(raw: ExpertRagConfig | null | undefined): {
  top_k: number;
  rerank_top_n: number;
  similarity_threshold: number;
} {
  return {
    top_k: typeof raw?.top_k === 'number' ? raw.top_k : RAG_CONFIG_DEFAULTS.top_k,
    rerank_top_n:
      typeof raw?.rerank_top_n === 'number' ? raw.rerank_top_n : RAG_CONFIG_DEFAULTS.rerank_top_n,
    similarity_threshold:
      typeof raw?.similarity_threshold === 'number'
        ? raw.similarity_threshold
        : RAG_CONFIG_DEFAULTS.similarity_threshold,
  };
}

/** Persist supported RAG knobs only. */
export function serializeRagConfig(values: {
  top_k: number;
  rerank_top_n: number;
  similarity_threshold: number;
}): ExpertRagConfig {
  return {
    top_k: values.top_k,
    rerank_top_n: values.rerank_top_n,
    similarity_threshold: values.similarity_threshold,
  };
}

export function clampRagValue(
  key: 'top_k' | 'rerank_top_n' | 'similarity_threshold',
  value: number,
): number {
  const bounds = RAG_CONFIG_BOUNDS[key];
  return Math.min(bounds.max, Math.max(bounds.min, value));
}
