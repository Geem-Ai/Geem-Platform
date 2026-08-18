import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import type { AppInstallation } from '@/services/api/apps';
import {
  localizeCatalogApp,
  localizeAppPlanName,
  resolveAppAccessBadge,
} from '../lib/billing-label';
import { AppBillingLabel } from './AppBillingLabel';
import { AppIcon } from './AppIcon';
import { AppInstallButton } from './AppInstallButton';
import { AppPurchaseButton } from './AppPurchaseButton';

function formatInstalledAt(value: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(
      new Date(value),
    );
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
  return `${formatDate(start, locale)} → ${formatDate(end, locale)}`;
}

export function InstalledAppCard({
  installation,
  canManage,
}: {
  installation: AppInstallation;
  canManage: boolean;
}) {
  const { t, i18n } = useTranslation();
  const app = installation.app;
  const localized = localizeCatalogApp(app, t);
  const access = app.access;
  const accessBadge = resolveAppAccessBadge(app);
  const usage = app.connection_usage;
  const summaries = app.connections ?? [];
  const periodRange = formatPeriodRange(
    access?.current_period_start,
    access?.current_period_end,
    i18n.language,
  );

  let commercialLabel: ReactNode = <AppBillingLabel app={app} />;
  if (app.billing_type === 'one_time' && access?.commercially_entitled) {
    commercialLabel = t('apps.billing.purchased');
  } else if (app.billing_type === 'subscription' && access?.plan_name) {
    commercialLabel =
      localizeAppPlanName(access.plan_code, access.plan_name, t) ?? access.plan_name;
  }

  return (
    <Card data-testid={`installed-app-${app.slug}`} className="shadow-none">
      <CardContent className="p-4 flex flex-col sm:flex-row gap-4 sm:items-start">
        <AppIcon
          slug={app.slug}
          name={localized.name}
          iconUrl={app.icon_url}
          size="md"
        />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold tracking-tight">
              {localized.name}
            </h3>
            <Badge
              variant={accessBadge.variant}
              appearance="light"
              size="sm"
              data-testid={`installed-access-badge-${app.slug}`}
            >
              {t(accessBadge.labelKey)}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground" data-testid="installed-plan-label">
            {app.billing_type === 'subscription' && access?.plan_name
              ? t('apps.billing.planLabel', { plan: commercialLabel })
              : commercialLabel}
          </p>
          {app.billing_type === 'subscription' && periodRange ? (
            <p className="text-sm text-muted-foreground" data-testid="installed-period-range">
              {access?.status === 'expired'
                ? t('apps.billing.expiredOn', {
                    date: formatDate(access.current_period_end, i18n.language),
                  })
                : t('apps.billing.currentPeriod', { range: periodRange })}
            </p>
          ) : app.billing_type === 'subscription' && access?.current_period_end ? (
            <p className="text-sm text-muted-foreground" data-testid="installed-period-end">
              {access.status === 'expired'
                ? t('apps.billing.expiredOn', {
                    date: formatDate(access.current_period_end, i18n.language),
                  })
                : t('apps.billing.activeUntil', {
                    date: formatDate(access.current_period_end, i18n.language),
                  })}
            </p>
          ) : null}
          <p className="text-sm text-muted-foreground">
            {t('apps.installedAt', {
              date: formatInstalledAt(installation.installed_at, i18n.language),
            })}
          </p>
          {usage && usage.limit != null ? (
            <p
              className="text-sm text-muted-foreground"
              data-testid={`installed-connection-usage-${app.slug}`}
            >
              {t('apps.connections.usage', {
                used: usage.used,
                limit: usage.limit,
              })}
            </p>
          ) : null}
          {summaries.length > 0 ? (
            <ul
              className="space-y-1 text-sm text-muted-foreground"
              data-testid={`installed-connection-list-${app.slug}`}
            >
              {summaries.map((conn) => (
                <li key={conn.id} className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant={
                      conn.status === 'active'
                        ? 'success'
                        : conn.status === 'error' || conn.status === 'revoked'
                          ? 'destructive'
                          : 'secondary'
                    }
                    appearance="light"
                    size="sm"
                  >
                    {t(`apps.connections.status.${conn.status}`, {
                      defaultValue: conn.status,
                    })}
                  </Badge>
                  <span className="truncate">
                    {conn.display_name ||
                      conn.external_account_name ||
                      t('apps.connections.untitled')}
                  </span>
                </li>
              ))}
            </ul>
          ) : app.connector ? (
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {app.has_active_connection ? (
                <Badge variant="success" appearance="light" size="sm">
                  {t('apps.connections.connected')}
                </Badge>
              ) : app.connection_status === 'error' ? (
                <Badge variant="destructive" appearance="light" size="sm">
                  {t('apps.connections.status.error')}
                </Badge>
              ) : app.connection_status === 'connecting' ||
                app.connection_status === 'pending' ? (
                <Badge variant="info" appearance="light" size="sm">
                  {t(`apps.connections.status.${app.connection_status}`)}
                </Badge>
              ) : app.connection_status === 'revoked' ? (
                <Badge variant="destructive" appearance="light" size="sm">
                  {t('apps.connections.status.revoked')}
                </Badge>
              ) : app.connection_status === 'disconnected' ? (
                <Badge variant="secondary" appearance="light" size="sm">
                  {t('apps.connections.reconnect')}
                </Badge>
              ) : (
                <Badge variant="secondary" appearance="light" size="sm">
                  {t('apps.connections.notConnected')}
                </Badge>
              )}
              {!app.connector.available ? (
                <span>{t('apps.connections.connectorAvailableSoon')}</span>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('apps.integrationLater')}
            </p>
          )}
          <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:flex-wrap">
            {access?.can_renew ? (
              <div data-testid={`installed-renew-${app.slug}`} className="sm:min-w-36">
                <AppPurchaseButton app={app} canManage={canManage} />
              </div>
            ) : null}
            <Button
              asChild
              variant="outline"
              size="sm"
              className="w-full sm:w-auto justify-center"
            >
              <Link to={`/apps/${app.slug}`}>{t('apps.manageView')}</Link>
            </Button>
            <AppInstallButton
              app={app}
              canManage={canManage}
              size="sm"
              className="w-full sm:w-auto justify-center"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
