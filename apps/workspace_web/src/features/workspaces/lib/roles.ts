import type { WorkspaceRole } from '@/services/api/types';

/** UX helpers only — backend WorkspacePolicy remains authoritative. */

export function canManageWorkspace(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function canManageMembers(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function canChangeMemberRoles(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function canPromoteToOwner(role: string | null | undefined): boolean {
  return role === 'owner';
}

export function canDeleteWorkspace(role: string | null | undefined): boolean {
  return role === 'owner';
}

export function canManageApiKeys(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function canDeleteStorageFiles(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function isWorkspaceRole(value: string): value is WorkspaceRole {
  return value === 'owner' || value === 'admin' || value === 'member';
}
