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

type TranslateFn = (
  key: string,
  options?: { defaultValue?: string },
) => string;

/** Localized label for a role summary (system key → i18n, else name). */
export function roleLabel(
  role: RoleSummary | string | null | undefined,
  t: TranslateFn,
): string {
  const summary = asRoleSummary(role);
  if (!summary) return '';
  const systemKey = summary.system_key;
  return systemKey
    ? t(`roles.${systemKey}`, { defaultValue: summary.name })
    : summary.name;
}
