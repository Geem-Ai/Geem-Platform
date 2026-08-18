import { useTranslation } from 'react-i18next';
import type { CatalogApp } from '@/services/api/apps';
import { localizeAppPlanName } from '../lib/billing-label';
import { AppInstallButton } from './AppInstallButton';
import { AppPurchaseButton } from './AppPurchaseButton';

function formatPeriodEnd(value: string | null | undefined, locale: string): string {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatPeriodRange(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: string,
): string | null {
  if (!start || !end) return null;
  return `${formatPeriodEnd(start, locale)} → ${formatPeriodEnd(end, locale)}`;
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
  const periodRange = formatPeriodRange(
    access.current_period_start,
    access.current_period_end,
    i18n.language,
  );

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

  if (access.status === 'entitled_not_installed') {
    return (
      <div
        className="rounded-xl border border-border bg-muted/30 px-4 py-3 space-y-2"
        data-testid="app-subscription-entitled-not-installed"
      >
        <p className="text-sm font-semibold">{t('apps.billing.subscribed')}</p>
        <p className="text-sm text-muted-foreground">
          {t('apps.billing.entitledNotInstalled')}
        </p>
        {planName ? (
          <p className="text-sm text-muted-foreground">
            {t('apps.billing.currentPlan')}: {planName}
          </p>
        ) : null}
        {periodRange ? (
          <p className="text-sm text-muted-foreground">
            {t('apps.billing.currentPeriod', { range: periodRange })}
          </p>
        ) : null}
        <AppInstallButton app={app} canManage={canManage} />
      </div>
    );
  }

  if (access.status === 'active') {
    return (
      <div
        className="rounded-xl border border-border bg-muted/30 px-4 py-3 space-y-2"
        data-testid="app-subscription-active"
      >
        <p className="text-sm font-semibold">{t('apps.billing.currentPlan')}</p>
        {planName ? (
          <p className="text-sm text-muted-foreground">{planName}</p>
        ) : null}
        {periodRange ? (
          <p className="text-sm text-muted-foreground">
            {t('apps.billing.currentPeriod', { range: periodRange })}
          </p>
        ) : access.current_period_end ? (
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
