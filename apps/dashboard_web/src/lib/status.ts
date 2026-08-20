import type { VariantProps } from 'class-variance-authority';
import type { badgeVariants } from '@/components/ui/badge';

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>;

export type StatusBadgeSpec = {
  labelKey: string;
  variant: BadgeVariant;
};

const WORKSPACE_STATUS: Record<string, StatusBadgeSpec> = {
  active: { labelKey: 'status.workspace.active', variant: 'success' },
  suspended: { labelKey: 'status.workspace.suspended', variant: 'warning' },
  archived: { labelKey: 'status.workspace.archived', variant: 'secondary' },
};

const USER_STATUS: Record<string, StatusBadgeSpec> = {
  active: { labelKey: 'status.user.active', variant: 'success' },
  disabled: { labelKey: 'status.user.disabled', variant: 'destructive' },
};

const PLATFORM_ROLE: Record<string, StatusBadgeSpec> = {
  admin: { labelKey: 'status.platformRole.admin', variant: 'info' },
  none: { labelKey: 'status.platformRole.none', variant: 'secondary' },
};

const KIND: Record<string, StatusBadgeSpec> = {
  tenant: { labelKey: 'status.kind.tenant', variant: 'secondary' },
  system: { labelKey: 'status.kind.system', variant: 'info' },
};

function lookup(map: Record<string, StatusBadgeSpec>, value: string, fallbackKey: string): StatusBadgeSpec {
  return map[value] ?? { labelKey: fallbackKey, variant: 'secondary' };
}

export function workspaceStatusBadge(status: string): StatusBadgeSpec {
  return lookup(WORKSPACE_STATUS, status, 'status.workspace.unknown');
}

export function userStatusBadge(status: string): StatusBadgeSpec {
  return lookup(USER_STATUS, status, 'status.user.unknown');
}

export function platformRoleBadge(role: string): StatusBadgeSpec {
  return lookup(PLATFORM_ROLE, role, 'status.platformRole.unknown');
}

export function workspaceKindBadge(kind: string): StatusBadgeSpec {
  return lookup(KIND, kind, 'status.kind.unknown');
}
