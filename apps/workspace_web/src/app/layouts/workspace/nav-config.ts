import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  AppWindow,
  CreditCard,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  Settings,
  Sparkles,
  Users,
} from 'lucide-react';

/** Leaf destinations always have `to`. Group parents omit it (label only). */
export type NavItem = {
  id: string;
  labelKey: string;
  icon: LucideIcon;
  to?: string;
  children?: NavItem[];
};

export const workspaceNav: NavItem[] = [
  { id: 'overview', labelKey: 'nav.overview', to: '/overview', icon: LayoutDashboard },
  { id: 'experts', labelKey: 'nav.experts', to: '/experts', icon: Sparkles },
  {
    id: 'api',
    labelKey: 'nav.api',
    icon: KeyRound,
    children: [
      { id: 'api-keys', labelKey: 'nav.apiKeys', to: '/api/keys', icon: KeyRound },
      { id: 'api-usage', labelKey: 'nav.usage', to: '/api/usage', icon: Activity },
    ],
  },
  { id: 'apps', labelKey: 'nav.apps', to: '/apps', icon: AppWindow },
  { id: 'members', labelKey: 'nav.members', to: '/members', icon: Users },
  { id: 'storage', labelKey: 'nav.storage', to: '/storage', icon: HardDrive },
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
      },
      { id: 'billing-usage', labelKey: 'nav.usage', to: '/billing/usage', icon: LayoutDashboard },
      { id: 'credits', labelKey: 'nav.credits', to: '/billing/credits', icon: CreditCard },
      {
        id: 'billing-history',
        labelKey: 'nav.billingHistory',
        to: '/billing/history',
        icon: CreditCard,
      },
    ],
  },
  { id: 'settings', labelKey: 'nav.settings', to: '/settings', icon: Settings },
];
