import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  AppWindow,
  Building2,
  CreditCard,
  RefreshCw,
  Sparkles,
  Users,
  Wallet,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDateTime } from '@/lib/dates';
import { formatInteger, formatMoney, formatTokens } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformDashboardSummary, platformQueryKeys } from '@/services/api/platform';

function MetricCard({
  title,
  value,
  hint,
  icon: Icon,
  to,
}: {
  title: string;
  value: string;
  hint?: string;
  icon: typeof Building2;
  to?: string;
}) {
  const body = (
    <Card className={cn(to && 'transition-colors hover:bg-muted/40')}>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({
    queryKey: platformQueryKeys.dashboardSummary,
    queryFn: fetchPlatformDashboardSummary,
    staleTime: 60_000,
  });

  const data = query.data;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6 md:p-8" data-testid="overview-page">
      <DocumentTitle title={t('overview.title')} />
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <p className="text-sm font-medium text-primary">{t('app.product')}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{t('overview.dashboardTitle')}</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{t('overview.dashboardContext')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}>
          <RefreshCw className={cn('size-4', query.isFetching && 'animate-spin')} aria-hidden />
          {t('common.refresh')}
        </Button>
      </header>

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : null}
      {query.isError ? (
        <p className="text-sm text-destructive">{getErrorMessage(query.error, t)}</p>
      ) : null}

      {data ? (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              title={t('overview.metrics.workspaces')}
              value={formatInteger(data.workspaces.total, i18n.language)}
              hint={t('overview.metrics.workspacesHint', {
                active: data.workspaces.active,
                disabled: data.workspaces.disabled,
              })}
              icon={Building2}
              to="/workspaces"
            />
            <MetricCard
              title={t('overview.metrics.users')}
              value={formatInteger(data.users.total, i18n.language)}
              hint={t('overview.metrics.usersHint', {
                active: data.users.active,
                disabled: data.users.disabled,
              })}
              icon={Users}
              to="/users"
            />
            <MetricCard
              title={t('overview.metrics.experts')}
              value={formatInteger(data.experts.published, i18n.language)}
              hint={t('overview.metrics.expertsHint', { draft: data.experts.draft })}
              icon={Sparkles}
              to="/experts"
            />
            <MetricCard
              title={t('overview.metrics.usage30d')}
              value={formatTokens(data.usage.billed_tokens_30d, i18n.language)}
              hint={t('overview.metrics.usage30dHint', {
                active: data.usage.active_workspaces_30d,
              })}
              icon={Activity}
              to="/usage"
            />
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <Card data-testid="overview-billing-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Wallet className="size-4" aria-hidden />
                  {t('overview.sections.billing')}
                </CardTitle>
                <CardDescription>{t('overview.sections.billingHint')}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.billing.activeSubscriptions')}</p>
                  <p className="text-lg font-semibold">
                    {formatInteger(data.billing.active_subscriptions, i18n.language)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.billing.pendingPurchases')}</p>
                  <p className="text-lg font-semibold">
                    {formatInteger(data.billing.pending_purchases, i18n.language)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.billing.paidVolume30d')}</p>
                  <p className="text-lg font-semibold">
                    {formatMoney(data.billing.paid_purchase_volume_30d)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.billing.failed30d')}</p>
                  <p className="text-lg font-semibold">
                    {formatInteger(data.billing.failed_purchases_30d, i18n.language)}
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card data-testid="overview-apps-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <AppWindow className="size-4" aria-hidden />
                  {t('overview.sections.apps')}
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.apps.published')}</p>
                  <p className="text-lg font-semibold">{formatInteger(data.apps.published, i18n.language)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.apps.installations')}</p>
                  <p className="text-lg font-semibold">{formatInteger(data.apps.installations, i18n.language)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.apps.activeSubscriptions')}</p>
                  <p className="text-lg font-semibold">
                    {formatInteger(data.apps.active_subscriptions, i18n.language)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">{t('overview.apps.activeLicenses')}</p>
                  <p className="text-lg font-semibold">
                    {formatInteger(data.apps.active_licenses, i18n.language)}
                  </p>
                </div>
              </CardContent>
            </Card>
          </section>

          <Card data-testid="overview-gateway-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <CreditCard className="size-4" aria-hidden />
                {t('overview.sections.gateway')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.gateway ? (
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-medium">{data.gateway.code}</span>
                  <Badge appearance="light">
                    {data.gateway.enabled ? t('paymentGateways.active') : t('paymentGateways.inactive')}
                  </Badge>
                  {data.gateway.test_mode ? (
                    <Badge variant="outline">{t('overview.gateway.testMode')}</Badge>
                  ) : null}
                  <Link to="/payment-gateways" className="text-sm text-primary hover:underline">
                    {t('overview.gateway.manage')}
                  </Link>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">{t('overview.gateway.none')}</p>
              )}
            </CardContent>
          </Card>

          <Card data-testid="overview-activity-card">
            <CardHeader>
              <CardTitle>{t('overview.sections.activity')}</CardTitle>
              <CardDescription>{t('overview.sections.activityHint')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.recent_activity.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('overview.activity.empty')}</p>
              ) : (
                data.recent_activity.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-col gap-1 rounded-lg border border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <p className="text-sm font-medium">{item.summary ?? item.action}</p>
                      <p className="text-xs text-muted-foreground">
                        {item.actor?.email ?? t('overview.activity.systemActor')} ·{' '}
                        {item.workspace?.name ?? t('overview.activity.platformScope')}
                      </p>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {formatAdminDateTime(item.created_at, i18n.language)}
                    </p>
                  </div>
                ))
              )}
              <Link to="/audit-logs" className="text-sm font-medium text-primary hover:underline">
                {t('overview.activity.viewAll')}
              </Link>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
