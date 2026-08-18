import type { WorkspaceSummary } from '@/services/api/types';
import { loadWorkspacePreference } from '@/services/auth/workspace-context';

/** UX only — Host slug, then last-selected preference, then /me current. */
export function pickInitialWorkspace(
  workspaces: WorkspaceSummary[],
  userId: string,
  hostSlug: string | null,
  meCurrent: WorkspaceSummary | null,
): WorkspaceSummary | null {
  if (workspaces.length === 0) return null;

  if (hostSlug) {
    const fromHost = workspaces.find((w) => w.slug === hostSlug);
    if (fromHost) return fromHost;
  }

  const pref = loadWorkspacePreference(userId);
  if (pref) {
    const fromPref = workspaces.find((w) => w.id === pref);
    if (fromPref) return fromPref;
  }

  if (meCurrent) {
    const match = workspaces.find((w) => w.id === meCurrent.id);
    if (match) return match;
  }

  return workspaces[0] ?? null;
}
