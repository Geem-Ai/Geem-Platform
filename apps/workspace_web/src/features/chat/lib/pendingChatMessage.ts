/**
 * First-message handoff from /chat → /chat/:id.
 * Survives React Strict Mode remounts (location.state is cleared too early otherwise).
 */

const storageKey = (conversationId: string) =>
  `geem:chat-pending:${conversationId}`;

/** In-flight guard across Strict Mode remounts (same JS realm). */
const inFlight = new Set<string>();

export function setPendingChatMessage(
  conversationId: string,
  content: string,
): void {
  const trimmed = content.trim();
  if (!conversationId || !trimmed) return;
  try {
    sessionStorage.setItem(storageKey(conversationId), trimmed);
  } catch {
    // private mode / quota — in-memory fallback below via Map
  }
  memory.set(conversationId, trimmed);
}

export function peekPendingChatMessage(conversationId: string): string | null {
  const fromMem = memory.get(conversationId);
  if (fromMem) return fromMem;
  try {
    return sessionStorage.getItem(storageKey(conversationId));
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

const memory = new Map<string, string>();
