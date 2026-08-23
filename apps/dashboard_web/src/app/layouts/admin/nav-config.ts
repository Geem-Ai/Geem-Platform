import type { LucideIcon } from 'lucide-react';
import {
  AppWindow,
  Building2,
  Coins,
  CreditCard,
  LayoutDashboard,
  Receipt,
  ScrollText,
  Sparkles,
  Activity,
  Users,
  Wallet,
} from 'lucide-react';

export type AdminNavItem = {
  id: string;
  labelKey: string;
  icon: LucideIcon;
  to?: string;
  phase?: string;
  children?: AdminNavItem[];
};

export const adminNav: AdminNavItem[] = [
  {
    id: 'overview',
    labelKey: 'nav.overview',
    to: '/',
    icon: LayoutDashboard,
  },
  {
    id: 'platform',
    labelKey: 'nav.platform',
    icon: Building2,
    children: [
      {
        id: 'workspaces',
        labelKey: 'nav.workspaces',
        to: '/workspaces',
        icon: Building2,
        phase: '12B',
      },
      {
        id: 'users',
        labelKey: 'nav.users',
        to: '/users',
        icon: Users,
        phase: '12B',
      },
    ],
  },
  {
    id: 'ai',
    labelKey: 'nav.ai',
    icon: Sparkles,
    children: [
      {
        id: 'platform-experts',
        labelKey: 'nav.platformExperts',
        to: '/experts',
        icon: Sparkles,
      },
      {
        id: 'usage',
        labelKey: 'nav.usage',
        to: '/usage',
        icon: Activity,
      },
    ],
  },
  {
    id: 'commerce',
    labelKey: 'nav.commerce',
    icon: CreditCard,
    children: [
      {
        id: 'plans',
        labelKey: 'nav.plans',
        to: '/plans',
        icon: Wallet,
      },
      {
        id: 'credits',
        labelKey: 'nav.credits',
        to: '/credits',
        icon: Coins,
      },
      {
        id: 'app-store',
        labelKey: 'nav.appStore',
        to: '/app-store',
        icon: AppWindow,
        phase: '12E',
      },
      {
        id: 'purchases',
        labelKey: 'nav.purchases',
        to: '/purchases',
        icon: Receipt,
      },
      {
        id: 'payment-gateways',
        labelKey: 'nav.paymentGateways',
        to: '/payment-gateways',
        icon: CreditCard,
      },
    ],
  },
  {
    id: 'operations',
    labelKey: 'nav.operations',
    icon: ScrollText,
    children: [
      {
        id: 'audit-logs',
        labelKey: 'nav.auditLogs',
        to: '/audit-logs',
        icon: ScrollText,
      },
    ],
  },
];

export function flattenAdminNav(items: AdminNavItem[] = adminNav): AdminNavItem[] {
  return items.flatMap((item) =>
    item.children?.length ? flattenAdminNav(item.children) : [item],
  );
}
