/**
 * First-message handoff from /chat → /chat/:id.
 * Survives React Strict Mode remounts (location.state is cleared too early otherwise).
 */

export type PendingChatPayload = {
  content: string;
  attachmentId?: string;
  attachmentMeta?: {
    id?: string;
    filename: string;
    mimeType: string;
    byteSize?: number;
  };
};

const storageKey = (conversationId: string) =>
  `geem:chat-pending:${conversationId}`;

/** In-flight guard across Strict Mode remounts (same JS realm). */
const inFlight = new Set<string>();
const memory = new Map<string, PendingChatPayload>();

function normalizePayload(
  contentOrPayload: string | PendingChatPayload,
): PendingChatPayload | null {
  if (typeof contentOrPayload === 'string') {
    const trimmed = contentOrPayload.trim();
    if (!trimmed) return null;
    return { content: trimmed };
  }
  const content = (contentOrPayload.content || '').trim();
  const attachmentId = contentOrPayload.attachmentId?.trim() || undefined;
  if (!content && !attachmentId) return null;
  return {
    content,
    attachmentId,
    attachmentMeta: contentOrPayload.attachmentMeta,
  };
}

export function setPendingChatMessage(
  conversationId: string,
  contentOrPayload: string | PendingChatPayload,
): void {
  const payload = normalizePayload(contentOrPayload);
  if (!conversationId || !payload) return;
  try {
    sessionStorage.setItem(storageKey(conversationId), JSON.stringify(payload));
  } catch {
    // private mode / quota — in-memory fallback below via Map
  }
  memory.set(conversationId, payload);
}

export function peekPendingChatMessage(
  conversationId: string,
): PendingChatPayload | null {
  const fromMem = memory.get(conversationId);
  if (fromMem) return fromMem;
  try {
    const raw = sessionStorage.getItem(storageKey(conversationId));
    if (!raw) return null;
    // Legacy: plain string content
    if (raw.startsWith('{')) {
      return normalizePayload(JSON.parse(raw) as PendingChatPayload);
    }
    return normalizePayload(raw);
  } catch {
    return null;
  }
}

export function clearPendingChatMessage(conversationId: string): void {
  memory.delete(conversationId);
  inFlight.delete(conversationId);
  try {
    sessionStorage.removeItem(storageKey(conversationId));
  } catch {
    // ignore
  }
}

export function beginPendingChatSend(conversationId: string): boolean {
  if (!conversationId || inFlight.has(conversationId)) return false;
  inFlight.add(conversationId);
  return true;
}

export function endPendingChatSend(conversationId: string): void {
  inFlight.delete(conversationId);
}
