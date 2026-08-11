/** Per-workspace last-used expert id in sessionStorage (optional convenience). */

const KEY_PREFIX = 'geem-last-expert:';

export function loadLastExpert(workspaceId: string): string | null {
  try {
    return sessionStorage.getItem(KEY_PREFIX + workspaceId);
  } catch {
    return null;
  }
}

export function saveLastExpert(workspaceId: string, expertId: string): void {
  try {
    sessionStorage.setItem(KEY_PREFIX + workspaceId, expertId);
  } catch {
    /* ignore quota errors */
  }
}

export function clearLastExpert(workspaceId: string): void {
  try {
    sessionStorage.removeItem(KEY_PREFIX + workspaceId);
  } catch {
    /* ignore */
  }
}
