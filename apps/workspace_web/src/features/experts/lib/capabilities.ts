/**
 * Expert UX capability helpers — UX gating only.
 * Backend ExpertPolicy remains the authoritative guard.
 */

import { WorkspacePermission } from '@/features/authz/permissions';

type Can = (permission: string) => boolean;

export function canCreateExpert(can: Can): boolean {
  return can(WorkspacePermission.EXPERTS_CREATE);
}

export function canEditExpert(can: Can, ownership: string): boolean {
  return can(WorkspacePermission.EXPERTS_UPDATE) && ownership === 'workspace';
}

export function canDeleteExpert(can: Can, ownership: string): boolean {
  return can(WorkspacePermission.EXPERTS_DELETE) && ownership === 'workspace';
}

export function canManageExpertKnowledge(can: Can, ownership: string): boolean {
  return (
    can(WorkspacePermission.EXPERTS_MANAGE_KNOWLEDGE) && ownership === 'workspace'
  );
}

export function canAskExpert(can: Can, status: string): boolean {
  return (
    can(WorkspacePermission.EXPERTS_USE) &&
    can(WorkspacePermission.CHAT_USE) &&
    status === 'ready'
  );
}
