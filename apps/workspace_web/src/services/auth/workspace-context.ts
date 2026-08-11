/**
 * Workspace context accessors for the API client.
 * Phase 1 will replace this with React context backed by FastAPI.
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
