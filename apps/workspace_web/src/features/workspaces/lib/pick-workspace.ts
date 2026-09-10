import type { WorkspaceSummary } from '@/services/api/types';
import { loadWorkspacePreference } from '@/services/auth/workspace-context';
import { activeWorkspaces } from '@/features/workspaces/lib/workspace-status';

/** UX only — Host slug, then last-selected preference, then /me current. Prefers active. */
export function pickInitialWorkspace(
  workspaces: WorkspaceSummary[],
  userId: string,
  hostSlug: string | null,
  meCurrent: WorkspaceSummary | null,
): WorkspaceSummary | null {
  const selectable = activeWorkspaces(workspaces);
  if (selectable.length === 0) return null;

  if (hostSlug) {
    const fromHost = selectable.find((w) => w.slug === hostSlug);
    if (fromHost) return fromHost;
  }

  const pref = loadWorkspacePreference(userId);
  if (pref) {
    const fromPref = selectable.find((w) => w.id === pref);
    if (fromPref) return fromPref;
  }

  if (meCurrent) {
    const match = selectable.find((w) => w.id === meCurrent.id);
    if (match) return match;
  }

  return selectable[0] ?? null;
}
