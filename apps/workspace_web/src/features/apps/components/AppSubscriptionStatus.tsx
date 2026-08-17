import { useTranslation } from 'react-i18next';
import type { CatalogApp } from '@/services/api/apps';
import { localizeAppPlanName } from '../lib/billing-label';
import { AppPurchaseButton } from './AppPurchaseButton';

function formatPeriodEnd(value: string | null | undefined, locale: string): string {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(value));
  } catch {
    return value;
  }
}

export function AppSubscriptionStatus({
  app,
  canManage,
}: {
  app: CatalogApp;
  canManage: boolean;
}) {
  const { t, i18n } = useTranslation();
  const access = app.access;
  if (!access || app.billing_type !== 'subscription') return null;
  const planName = localizeAppPlanName(access.plan_code, access.plan_name, t);

  if (access.status === 'expired') {
    return (
      <div
        className="rounded-xl border border-border bg-muted/30 px-4 py-3 space-y-2"
        data-testid="app-subscription-expired"
      >
        <p className="text-sm font-semibold">{t('apps.billing.subscriptionExpired')}</p>
        {planName ? (
          <p className="text-sm text-muted-foreground">
            {t('apps.billing.previousPlan')}: {planName}
          </p>
        ) : null}
        {access.current_period_end ? (
          <p className="text-sm text-muted-foreground">
            {t('apps.billing.expiredOn', {
              date: formatPeriodEnd(access.current_period_end, i18n.language),
            })}
          </p>
        ) : null}
        <AppPurchaseButton app={app} canManage={canManage} />
      </div>
    );
  }

  if (
    access.status === 'active' ||
    access.status === 'entitled_not_installed'
  ) {
    return (
      <div
        className="rounded-xl border border-border bg-muted/30 px-4 py-3 space-y-2"
        data-testid="app-subscription-active"
      >
        <p className="text-sm font-semibold">{t('apps.billing.currentPlan')}</p>
        {planName ? (
          <p className="text-sm text-muted-foreground">{planName}</p>
        ) : null}
        {access.current_period_end ? (
          <p className="text-sm text-muted-foreground">
            {t('apps.billing.activeUntil', {
              date: formatPeriodEnd(access.current_period_end, i18n.language),
            })}
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">{t('apps.billing.manualRenewal')}</p>
        <AppPurchaseButton app={app} canManage={canManage} />
      </div>
    );
  }

  return null;
}
