import type { ApiErrorCode } from '@/services/api/errors';
import type {
  Citation,
  ConversationMessage,
  MessageAttachment,
  MessageRole,
  MessageStatus,
} from '@/services/api/types';

export type ChatUiAttachment = {
  id: string;
  filename: string;
  mime_type: string;
  byte_size: number;
};

/** UI message — may be optimistic (client-*) until reconciled with server IDs. */
export type ChatUiMessage = {
  id: string;
  clientId?: string;
  role: MessageRole | string;
  content: string;
  citations: Citation[];
  attachments?: ChatUiAttachment[];
  status: MessageStatus | string;
  created_at: string;
  errorMessage?: string | null;
  errorCode?: ApiErrorCode | null;
};

function mapAttachments(list: MessageAttachment[] | undefined): ChatUiAttachment[] {
  if (!list?.length) return [];
  return list.map((a) => ({
    id: String(a.id),
    filename: a.filename,
    mime_type: a.mime_type,
    byte_size: a.byte_size ?? 0,
  }));
}

export function toChatUiMessage(msg: ConversationMessage): ChatUiMessage {
  return {
    id: msg.id,
    role: msg.role,
    content: msg.content,
    citations: msg.citations ?? [],
    attachments: mapAttachments(msg.attachments),
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
