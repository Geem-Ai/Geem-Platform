import type { WorkspaceSummary } from '@/services/api/types';

export function isActiveWorkspace(workspace: {
  status: string;
}): boolean {
  return workspace.status === 'active';
}

export function isPendingWorkspace(workspace: {
  status: string;
}): boolean {
  return workspace.status === 'pending';
}

export function activeWorkspaces(
  workspaces: WorkspaceSummary[],
): WorkspaceSummary[] {
  return workspaces.filter(isActiveWorkspace);
}

export function hasActiveWorkspace(workspaces: WorkspaceSummary[]): boolean {
  return workspaces.some(isActiveWorkspace);
}

/** True when the user has memberships but none are usable yet. */
export function needsWorkspaceApproval(
  workspaces: WorkspaceSummary[],
): boolean {
  return workspaces.length > 0 && !hasActiveWorkspace(workspaces);
}
