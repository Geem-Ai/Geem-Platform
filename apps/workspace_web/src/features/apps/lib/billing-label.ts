import type { TFunction } from 'i18next';
import type { AppPlan, CatalogApp } from '@/services/api/apps';
import { formatMoney } from '@/features/billing/lib/money';

/** Billing label from backend plan/app data — never hardcode product prices. */
export function formatAppBillingLabel(
  app: Pick<CatalogApp, 'billing_type' | 'status' | 'plans'>,
  t: TFunction,
): string {
  if (app.status === 'coming_soon') {
    return t('apps.billing.comingSoon');
  }

  if (app.billing_type === 'free') {
    return t('apps.billing.free');
  }

  const plans = (app.plans ?? []).filter((p) => p.is_default || true);
  const priced = plans.filter((p) => Number(p.price_amount) > 0);

  if (app.billing_type === 'one_time') {
    const plan = pickDefaultPlan(priced) ?? pickDefaultPlan(plans);
    if (!plan || Number(plan.price_amount) <= 0) {
      return t('apps.billing.oneTime');
    }
    return t('apps.billing.oneTimePrice', {
      amount: formatMoney(plan.price_amount, plan.currency),
    });
  }

  if (app.billing_type === 'subscription') {
    const monthly = priced.filter((p) => p.billing_interval === 'monthly');
    const plan = pickLowest(monthly) ?? pickDefaultPlan(plans);
    if (!plan || Number(plan.price_amount) <= 0) {
      return t('apps.billing.subscription');
    }
    return t('apps.billing.fromMonthly', {
      amount: formatMoney(plan.price_amount, plan.currency),
    });
  }

  return t('apps.billing.unavailable');
}

function pickDefaultPlan(plans: AppPlan[]): AppPlan | undefined {
  return plans.find((p) => p.is_default) ?? plans[0];
}

function pickLowest(plans: AppPlan[]): AppPlan | undefined {
  if (!plans.length) return undefined;
  return [...plans].sort((a, b) =>
    a.price_amount.localeCompare(b.price_amount, 'en', { numeric: true }),
  )[0];
}

export function localizeCatalogApp(
  app: Pick<CatalogApp, 'slug' | 'name' | 'short_description' | 'description'>,
  t: TFunction,
): { name: string; shortDescription: string; description: string | null } {
  const nameKey = `apps.catalog.${app.slug}.name`;
  const shortKey = `apps.catalog.${app.slug}.shortDescription`;
  const descKey = `apps.catalog.${app.slug}.description`;
  const name = t(nameKey, { defaultValue: app.name });
  const shortDescription = t(shortKey, { defaultValue: app.short_description });
  const description = app.description
    ? t(descKey, { defaultValue: app.description })
    : null;
  return { name, shortDescription, description };
}

/** Localize seeded plan copy by stable plan code; fall back to API strings. */
export function localizeAppPlan(
  plan: Pick<AppPlan, 'code' | 'name' | 'description'>,
  t: TFunction,
): { name: string; description: string | null } {
  const name = t(`apps.planCatalog.${plan.code}.name`, {
    defaultValue: plan.name,
  });
  const description = plan.description
    ? t(`apps.planCatalog.${plan.code}.description`, {
        defaultValue: plan.description,
      })
    : null;
  return { name, description };
}

/** Localize plan display name when only code + API name are available (e.g. access). */
export function localizeAppPlanName(
  code: string | null | undefined,
  name: string | null | undefined,
  t: TFunction,
): string | null {
  if (!name && !code) return null;
  if (code) {
    return t(`apps.planCatalog.${code}.name`, { defaultValue: name ?? code });
  }
  return name ?? null;
}

/** Format an app plan entitlement line for display. */
export function formatAppEntitlement(
  key: string,
  value: unknown,
  t: TFunction,
): string {
  const count = typeof value === 'number' ? value : Number(value);
  return t(`apps.entitlements.${key}`, {
    count: Number.isFinite(count) ? count : 0,
    value: String(value),
    defaultValue: t('apps.entitlements.other', {
      key,
      value: String(value),
    }),
  });
}

export function appIconSrc(iconUrl: string | null | undefined): string | null {
  if (!iconUrl) return null;
  if (iconUrl.startsWith('http://') || iconUrl.startsWith('https://')) {
    return iconUrl;
  }
  return iconUrl.startsWith('/') ? iconUrl : `/${iconUrl}`;
}
