import { describe, expect, it } from 'vitest';
import i18n from '@/lib/i18n';
import type { CatalogApp } from '@/services/api/apps';
import {
  formatAppBillingLabel,
  formatAppEntitlement,
  localizeAppPlan,
  localizeAppPlanName,
} from './billing-label';

function app(partial: Partial<CatalogApp>): CatalogApp {
  return {
    id: '1',
    slug: 'demo',
    name: 'Demo',
    short_description: 'x',
    description: null,
    category: {
      slug: 'knowledge',
      name_key: 'apps.categories.knowledge',
      description_key: null,
      icon: null,
      sort_order: 0,
    },
    icon_url: null,
    billing_type: 'free',
    status: 'published',
    is_featured: false,
    sort_order: 0,
    plans: [],
    installation: null,
    installation_status: null,
    can_install: true,
    can_uninstall: false,
    access_requirement: 'free',
    access: null,
    connector: null,
    has_active_connection: false,
    ...partial,
  };
}

describe('formatAppBillingLabel', () => {
  it('renders free badge copy', () => {
    expect(formatAppBillingLabel(app({ billing_type: 'free' }), i18n.t)).toBe(
      i18n.t('apps.billing.free'),
    );
  });

  it('renders coming soon for coming_soon status', () => {
    expect(
      formatAppBillingLabel(
        app({ status: 'coming_soon', billing_type: 'subscription' }),
        i18n.t,
      ),
    ).toBe(i18n.t('apps.billing.comingSoon'));
  });

  it('formats one-time price from backend plan', () => {
    const label = formatAppBillingLabel(
      app({
        billing_type: 'one_time',
        plans: [
          {
            id: 'p1',
            code: 'buy',
            name: 'Buy',
            description: null,
            billing_interval: 'none',
            price_amount: '299.00',
            currency: 'SAR',
            is_default: true,
            entitlements: {},
          },
        ],
      }),
      i18n.t,
    );
    expect(label).toContain('299.00');
    expect(label).toContain('SAR');
  });

  it('formats subscription from monthly plan', () => {
    const label = formatAppBillingLabel(
      app({
        billing_type: 'subscription',
        status: 'published',
        plans: [
          {
            id: 'p1',
            code: 'starter',
            name: 'Starter',
            description: null,
            billing_interval: 'monthly',
            price_amount: '49.00',
            currency: 'SAR',
            is_default: true,
            entitlements: {},
          },
        ],
      }),
      i18n.t,
    );
    expect(label).toContain('49.00');
  });

  it('subscription without prices shows generic subscription label', () => {
    expect(
      formatAppBillingLabel(
        app({
          billing_type: 'subscription',
          status: 'published',
          plans: [],
        }),
        i18n.t,
      ),
    ).toBe(i18n.t('apps.billing.subscription'));
  });
});

describe('localizeAppPlan', () => {
  it('translates free plan copy in Arabic', async () => {
    await i18n.changeLanguage('ar');
    const localized = localizeAppPlan(
      {
        code: 'free',
        name: 'Free',
        description:
          'Included at no cost. Provider connection setup comes in a later phase.',
      },
      i18n.t,
    );
    expect(localized.name).toBe(i18n.t('apps.planCatalog.free.name'));
    expect(localized.description).toBe(
      i18n.t('apps.planCatalog.free.description'),
    );
  });

  it('falls back to API strings for unknown plan codes', async () => {
    await i18n.changeLanguage('en');
    const localized = localizeAppPlan(
      { code: 'custom-pro', name: 'Pro', description: 'Custom plan' },
      i18n.t,
    );
    expect(localized.name).toBe('Pro');
    expect(localized.description).toBe('Custom plan');
  });
});

describe('localizeAppPlanName', () => {
  it('uses plan code translations when available', async () => {
    await i18n.changeLanguage('ar');
    expect(localizeAppPlanName('free', 'Free', i18n.t)).toBe(
      i18n.t('apps.planCatalog.free.name'),
    );
  });
});

describe('formatAppEntitlement', () => {
  it('formats known entitlements in Arabic', async () => {
    await i18n.changeLanguage('ar');
    expect(formatAppEntitlement('connections', 1, i18n.t)).toBe(
      i18n.t('apps.entitlements.connections', { count: 1 }),
    );
  });
});
