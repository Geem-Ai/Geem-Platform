/**
 * Conversation API client (Phase 4A CRUD + Phase 4B stream + Phase 4C Chat UX).
 */

import type {
  Conversation,
  ConversationMessage,
} from './types';
import { apiRequest } from './client';
import { streamSse, type SseHandlers } from './sse';

export type ConversationCreateInput = {
  expert_id: string;
  title?: string | null;
};

export type ConversationUpdateInput = {
  title?: string | null;
  is_pinned?: boolean;
};

export function listConversations(params?: { limit?: number; offset?: number }) {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set('limit', String(params.limit));
  if (params?.offset != null) qs.set('offset', String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : '';
  return apiRequest<Conversation[]>(`/api/conversations${suffix}`);
}

export function getConversation(conversationId: string) {
  return apiRequest<Conversation>(`/api/conversations/${conversationId}`);
}

export function createConversation(input: ConversationCreateInput) {
  return apiRequest<Conversation>('/api/conversations', {
    method: 'POST',
    json: input,
  });
}

export function updateConversation(conversationId: string, input: ConversationUpdateInput) {
  return apiRequest<Conversation>(`/api/conversations/${conversationId}`, {
    method: 'PATCH',
    json: input,
  });
}

export function deleteConversation(conversationId: string) {
  return apiRequest<void>(`/api/conversations/${conversationId}`, { method: 'DELETE' });
}

export function listConversationMessages(
  conversationId: string,
  params?: { limit?: number; offset?: number },
) {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set('limit', String(params.limit));
  if (params?.offset != null) qs.set('offset', String(params.offset));
  const suffix = qs.toString() ? `?${qs}` : '';
  return apiRequest<ConversationMessage[]>(
    `/api/conversations/${conversationId}/messages${suffix}`,
  );
}

/** Phase 4B — persisted conversation turn SSE. */
export function streamConversationMessage(
  conversationId: string,
  content: string,
  handlers: SseHandlers,
  signal?: AbortSignal,
) {
  return streamSse(
    `/api/conversations/${conversationId}/messages/stream`,
    { content },
    handlers,
    signal,
  );
}

/** Phase 4B — retry failed/cancelled assistant without a new user message. */
export function retryConversationMessageStream(
  conversationId: string,
  assistantMessageId: string,
  handlers: SseHandlers,
  signal?: AbortSignal,
) {
  return streamSse(
    `/api/conversations/${conversationId}/messages/${assistantMessageId}/retry/stream`,
    {},
    handlers,
    signal,
  );
}
