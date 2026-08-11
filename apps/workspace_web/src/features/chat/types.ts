import type {
  Citation,
  ConversationMessage,
  MessageRole,
  MessageStatus,
} from '@/services/api/types';

/** UI message — may be optimistic (client-*) until reconciled with server IDs. */
export type ChatUiMessage = {
  id: string;
  clientId?: string;
  role: MessageRole | string;
  content: string;
  citations: Citation[];
  status: MessageStatus | string;
  created_at: string;
  errorMessage?: string | null;
};

export function toChatUiMessage(msg: ConversationMessage): ChatUiMessage {
  return {
    id: msg.id,
    role: msg.role,
    content: msg.content,
    citations: msg.citations ?? [],
    status: msg.status,
    created_at: msg.created_at,
  };
}

export function newClientId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
