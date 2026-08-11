/**
 * Module-level workspace hint for the API client.
 * React WorkspaceProvider keeps this in sync.
 *
 * Header policy (Phase 1B):
 * - X-Workspace-Id: sent when a workspace is selected (routing hint; not auth).
 * - X-Workspace-Slug: sent only in local/dev (backend ignores unless APP_ENV=local).
 * Production tenant hostnames resolve on the backend from Host; Id is still a hint.
 */

export type WorkspaceContextSnapshot = {
  workspaceId: string | null;
  workspaceSlug: string | null;
};

let snapshot: WorkspaceContextSnapshot = {
  workspaceId: null,
  workspaceSlug: null,
};

export function getWorkspaceContext(): WorkspaceContextSnapshot {
  return snapshot;
}

export function setWorkspaceContext(
  next: Partial<WorkspaceContextSnapshot>,
): void {
  snapshot = { ...snapshot, ...next };
}

export function clearWorkspaceContext(): void {
  snapshot = { workspaceId: null, workspaceSlug: null };
}

/** Persist last-selected workspace id per user (UX preference only). */
const PREF_PREFIX = 'geem-workspace-pref:';

export function loadWorkspacePreference(userId: string): string | null {
  try {
    return localStorage.getItem(`${PREF_PREFIX}${userId}`);
  } catch {
    return null;
  }
}

export function saveWorkspacePreference(userId: string, workspaceId: string): void {
  try {
    localStorage.setItem(`${PREF_PREFIX}${userId}`, workspaceId);
  } catch {
    // ignore quota / private mode
  }
}

export function clearWorkspacePreference(userId: string): void {
  try {
    localStorage.removeItem(`${PREF_PREFIX}${userId}`);
  } catch {
    // ignore
  }
}
