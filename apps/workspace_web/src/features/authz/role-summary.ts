import type { RoleSummary } from '@/services/api/types';

export function asRoleSummary(
  role: RoleSummary | string | null | undefined,
): RoleSummary | null {
  if (!role) return null;
  if (typeof role === 'string') {
    return {
      id: '',
      name: role,
      is_system: true,
      is_owner_role: role === 'owner',
      system_key: role,
    };
  }
  return role;
}

export function isOwnerRole(
  role: RoleSummary | string | null | undefined,
): boolean {
  const summary = asRoleSummary(role);
  return Boolean(summary?.is_owner_role || summary?.system_key === 'owner');
}

export function roleDisplayName(
  role: RoleSummary | string | null | undefined,
): string {
  const summary = asRoleSummary(role);
  return summary?.name ?? '';
}

export function roleSystemKey(
  role: RoleSummary | string | null | undefined,
): string | null {
  return asRoleSummary(role)?.system_key ?? null;
}
