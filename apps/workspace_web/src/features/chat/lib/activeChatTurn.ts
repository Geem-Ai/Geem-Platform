import type { ChatUiMessage } from '../types';
import { newClientId } from '../types';

export type ActiveChatTurn = {
  conversationId: string;
  messages: ChatUiMessage[];
  isStreaming: boolean;
  userClientId: string;
  assistantClientId: string;
  content: string;
};

let active: ActiveChatTurn | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function subscribeActiveChatTurn(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getActiveChatTurn(
  conversationId: string | null | undefined,
): ActiveChatTurn | null {
  if (!conversationId || !active) return null;
  return active.conversationId === conversationId ? active : null;
}

export function buildOptimisticTurnMessages(
  content: string,
  ids?: { userClientId?: string; assistantClientId?: string },
): {
  messages: ChatUiMessage[];
  userClientId: string;
  assistantClientId: string;
} {
  const userClientId = ids?.userClientId ?? newClientId('client-user');
  const assistantClientId =
    ids?.assistantClientId ?? newClientId('client-assistant');
  const now = new Date().toISOString();
  return {
    userClientId,
    assistantClientId,
    messages: [
      {
        id: userClientId,
        clientId: userClientId,
        role: 'user',
        content,
        citations: [],
        status: 'completed',
        created_at: now,
      },
      {
        id: assistantClientId,
        clientId: assistantClientId,
        role: 'assistant',
        content: '',
        citations: [],
        status: 'streaming',
        created_at: now,
      },
    ],
  };
}

/** Publish/replace the active in-flight turn (survives Strict Mode remounts). */
export function publishActiveChatTurn(input: ActiveChatTurn): ActiveChatTurn {
  active = input;
  emit();
  return active;
}

/** Ensure a visible user + streaming assistant pair exists for this conversation. */
export function ensureActiveChatTurn(
  conversationId: string,
  content: string,
): ActiveChatTurn {
  const trimmed = content.trim();
  if (
    active &&
    active.conversationId === conversationId &&
    active.content === trimmed
  ) {
    return active;
  }
  const built = buildOptimisticTurnMessages(trimmed);
  return publishActiveChatTurn({
    conversationId,
    content: trimmed,
    messages: built.messages,
    isStreaming: true,
    userClientId: built.userClientId,
    assistantClientId: built.assistantClientId,
  });
}

export function patchActiveChatTurn(
  conversationId: string,
  patch: Partial<Pick<ActiveChatTurn, 'messages' | 'isStreaming'>>,
): void {
  if (!active || active.conversationId !== conversationId) return;
  active = { ...active, ...patch };
  emit();
}

export function clearActiveChatTurn(conversationId: string): void {
  if (!active || active.conversationId !== conversationId) return;
  active = null;
  emit();
}
