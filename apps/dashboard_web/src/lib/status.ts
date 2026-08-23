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

const PLAN_STATUS: Record<string, StatusBadgeSpec> = {
  active: { labelKey: 'status.plan.active', variant: 'success' },
  archived: { labelKey: 'status.plan.archived', variant: 'secondary' },
};

const EXPERT_STATUS: Record<string, StatusBadgeSpec> = {
  draft: { labelKey: 'experts.status.draft', variant: 'secondary' },
  ready: { labelKey: 'experts.status.ready', variant: 'success' },
  processing: { labelKey: 'experts.status.processing', variant: 'info' },
  failed: { labelKey: 'experts.status.failed', variant: 'destructive' },
  disabled: { labelKey: 'experts.status.disabled', variant: 'warning' },
};

const EXPERT_VISIBILITY: Record<string, StatusBadgeSpec> = {
  platform_draft: { labelKey: 'experts.visibility.draft', variant: 'secondary' },
  platform_published: { labelKey: 'experts.visibility.published', variant: 'success' },
};

const PURCHASE_STATUS: Record<string, StatusBadgeSpec> = {
  pending: { labelKey: 'purchases.status.pending', variant: 'warning' },
  redirected: { labelKey: 'purchases.status.redirected', variant: 'info' },
  paid: { labelKey: 'purchases.status.paid', variant: 'success' },
  failed: { labelKey: 'purchases.status.failed', variant: 'destructive' },
  cancelled: { labelKey: 'purchases.status.cancelled', variant: 'secondary' },
  expired: { labelKey: 'purchases.status.expired', variant: 'secondary' },
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

export function planStatusBadge(status: string): StatusBadgeSpec {
  return lookup(PLAN_STATUS, status, 'status.plan.unknown');
}

export function expertStatusBadge(status: string): StatusBadgeSpec {
  return lookup(EXPERT_STATUS, status, 'experts.status.unknown');
}

export function expertVisibilityBadge(visibility: string): StatusBadgeSpec {
  return lookup(EXPERT_VISIBILITY, visibility, 'experts.visibility.unknown');
}

export function purchaseStatusBadge(status: string): StatusBadgeSpec {
  return lookup(PURCHASE_STATUS, status, 'purchases.status.pending');
}
