import type { QueryResponse } from './types';
import { apiRequest } from './client';
import { streamSse, type SseHandlers } from './sse';

/**
 * Expert-scoped RAG query (Phase 3B).
 * Auth + workspace headers come from the shared API client.
 * Product retrieval is by expert_id — document_ids are no longer accepted.
 */
export function queryExpert(question: string, expertId: string, topK?: number) {
  return apiRequest<QueryResponse>('/api/query', {
    method: 'POST',
    json: {
      question,
      expert_id: expertId,
      top_k: topK,
    },
  });
}

export function queryExpertStream(
  question: string,
  expertId: string,
  handlers: SseHandlers,
  signal?: AbortSignal,
) {
  return streamSse(
    '/api/query/stream',
    {
      question,
      expert_id: expertId,
    },
    handlers,
    signal,
  );
}

/** @deprecated Phase 3B — use queryExpert. Kept temporarily for rename clarity. */
export const queryDocuments = (question: string, expertId: string, topK?: number) =>
  queryExpert(question, expertId, topK);

/** @deprecated Phase 3B — use queryExpertStream. */
export const queryDocumentsStream = (
  question: string,
  expertId: string,
  handlers: SseHandlers,
  signal?: AbortSignal,
) => queryExpertStream(question, expertId, handlers, signal);
