import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  AppWindow,
  CreditCard,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Sparkles,
  Users,
} from 'lucide-react';
import { WorkspacePermission } from '@/features/authz/permissions';

/** Leaf destinations always have `to`. Group parents omit it (label only). */
export type NavItem = {
  id: string;
  labelKey: string;
  icon: LucideIcon;
  to?: string;
  children?: NavItem[];
  /** Any of these permissions shows the item. Empty = visible to every member. */
  permissions?: string[];
};

export const workspaceNav: NavItem[] = [
  {
    id: 'overview',
    labelKey: 'nav.overview',
    to: '/overview',
    icon: LayoutDashboard,
    permissions: [WorkspacePermission.WORKSPACE_VIEW],
  },
  {
    id: 'chat',
    labelKey: 'nav.chat',
    to: '/chat',
    icon: MessageSquare,
    permissions: [WorkspacePermission.CHAT_USE],
  },
  {
    id: 'experts',
    labelKey: 'nav.experts',
    to: '/experts',
    icon: Sparkles,
    permissions: [WorkspacePermission.EXPERTS_VIEW],
  },
  {
    id: 'api',
    labelKey: 'nav.api',
    icon: KeyRound,
    children: [
      {
        id: 'api-keys',
        labelKey: 'nav.apiKeys',
        to: '/api/keys',
        icon: KeyRound,
        permissions: [WorkspacePermission.API_KEYS_VIEW],
      },
      {
        id: 'api-usage',
        labelKey: 'nav.usage',
        to: '/api/usage',
        icon: Activity,
        permissions: [WorkspacePermission.API_USAGE_VIEW],
      },
    ],
  },
  {
    id: 'apps',
    labelKey: 'nav.apps',
    to: '/apps',
    icon: AppWindow,
    permissions: [WorkspacePermission.APPS_VIEW],
  },
  {
    id: 'members',
    labelKey: 'nav.members',
    to: '/members',
    icon: Users,
    permissions: [WorkspacePermission.MEMBERS_VIEW],
  },
  {
    id: 'storage',
    labelKey: 'nav.storage',
    to: '/storage',
    icon: HardDrive,
    permissions: [WorkspacePermission.STORAGE_VIEW],
  },
  {
    id: 'billing',
    labelKey: 'nav.billing',
    icon: CreditCard,
    children: [
      {
        id: 'subscription',
        labelKey: 'nav.subscription',
        to: '/billing/subscription',
        icon: CreditCard,
        permissions: [WorkspacePermission.BILLING_VIEW],
      },
      {
        id: 'billing-usage',
        labelKey: 'nav.usage',
        to: '/billing/usage',
        icon: LayoutDashboard,
        permissions: [WorkspacePermission.BILLING_VIEW],
      },
      {
        id: 'credits',
        labelKey: 'nav.credits',
        to: '/billing/credits',
        icon: CreditCard,
        permissions: [WorkspacePermission.BILLING_VIEW],
      },
      {
        id: 'billing-history',
        labelKey: 'nav.billingHistory',
        to: '/billing/history',
        icon: CreditCard,
        permissions: [WorkspacePermission.BILLING_VIEW],
      },
    ],
  },
  {
    id: 'settings',
    labelKey: 'nav.settings',
    to: '/settings',
    icon: Settings,
    permissions: [WorkspacePermission.WORKSPACE_SETTINGS_VIEW],
  },
];
