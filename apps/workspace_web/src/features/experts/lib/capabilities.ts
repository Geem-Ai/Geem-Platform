/**
 * Expert UX capability helpers — UX gating only.
 * Backend ExpertPolicy remains the authoritative guard.
 */

export function canCreateExpert(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'admin';
}

export function canEditExpert(
  role: string | null | undefined,
  ownership: string,
): boolean {
  return (role === 'owner' || role === 'admin') && ownership === 'workspace';
}

export function canDeleteExpert(
  role: string | null | undefined,
  ownership: string,
): boolean {
  return (role === 'owner' || role === 'admin') && ownership === 'workspace';
}

export function canManageExpertKnowledge(
  role: string | null | undefined,
  ownership: string,
): boolean {
  return (role === 'owner' || role === 'admin') && ownership === 'workspace';
}

export function canAskExpert(status: string): boolean {
  return status === 'ready';
}
