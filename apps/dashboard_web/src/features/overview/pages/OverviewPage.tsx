import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  AppWindow,
  Building2,
  ChevronRight,
  CreditCard,
  RefreshCw,
  ScrollText,
  Sparkles,
  Users,
  Wallet,
} from 'lucide-react';
import { AdminMetricCard, AdminSnapshotStat } from '@/components/shared/AdminMetricCard';
import { AdminCardHeader, AdminSnapshotCard } from '@/components/shared/AdminSnapshotCard';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { formatAdminDateTime } from '@/lib/dates';
import { formatInteger, formatMoney, formatTokens } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformDashboardSummary, platformQueryKeys } from '@/services/api/platform';

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({
    queryKey: platformQueryKeys.dashboardSummary,
    queryFn: fetchPlatformDashboardSummary,
    staleTime: 60_000,
  });

  const data = query.data;
  const loading = query.isLoading;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6 md:p-8" data-testid="overview-page">
      <DocumentTitle title={t('overview.title')} />
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            {t('app.product')}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">{t('overview.dashboardTitle')}</h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            {t('overview.dashboardContext')}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          <RefreshCw className={cn('size-4', query.isFetching && 'animate-spin')} aria-hidden />
          {t('common.refresh')}
        </Button>
      </header>

      {query.isError ? (
        <p className="text-sm text-destructive">{getErrorMessage(query.error, t)}</p>
      ) : null}

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('overview.metrics.sectionLabel')}
        data-testid="overview-metrics"
      >
        <AdminMetricCard
          icon={Building2}
          tone="primary"
          label={t('overview.metrics.workspaces')}
          value={data ? formatInteger(data.workspaces.total, i18n.language) : '—'}
          hint={
            data
              ? t('overview.metrics.workspacesHint', {
                  active: data.workspaces.active,
                  disabled: data.workspaces.disabled,
                })
              : undefined
          }
          loading={loading}
          to="/workspaces"
          testId="overview-metric-workspaces"
        />
        <AdminMetricCard
          icon={Users}
          tone="info"
          label={t('overview.metrics.users')}
          value={data ? formatInteger(data.users.total, i18n.language) : '—'}
          hint={
            data
              ? t('overview.metrics.usersHint', {
                  active: data.users.active,
                  disabled: data.users.disabled,
                })
              : undefined
          }
          loading={loading}
          to="/users"
          testId="overview-metric-users"
        />
        <AdminMetricCard
          icon={Sparkles}
          tone="success"
          label={t('overview.metrics.experts')}
          value={data ? formatInteger(data.experts.published, i18n.language) : '—'}
          hint={
            data ? t('overview.metrics.expertsHint', { draft: data.experts.draft }) : undefined
          }
          loading={loading}
          to="/experts"
          testId="overview-metric-experts"
        />
        <AdminMetricCard
          icon={Activity}
          tone="warning"
          label={t('overview.metrics.usage30d')}
          value={data ? formatTokens(data.usage.billed_tokens_30d, i18n.language) : '—'}
          hint={
            data
              ? t('overview.metrics.usage30dHint', {
                  active: data.usage.active_workspaces_30d,
                })
              : undefined
          }
          loading={loading}
          to="/usage"
          testId="overview-metric-usage"
        />
      </section>

      {data ? (
        <>
          <section className="grid gap-3 lg:grid-cols-2">
            <AdminSnapshotCard
              icon={Wallet}
              title={t('overview.sections.billing')}
              description={t('overview.sections.billingHint')}
              tone="primary"
              testId="overview-billing-card"
            >
              <AdminSnapshotStat
                label={t('overview.billing.activeSubscriptions')}
                value={formatInteger(data.billing.active_subscriptions, i18n.language)}
              />
              <AdminSnapshotStat
                label={t('overview.billing.pendingPurchases')}
                value={formatInteger(data.billing.pending_purchases, i18n.language)}
              />
              <AdminSnapshotStat
                label={t('overview.billing.paidVolume30d')}
                value={formatMoney(data.billing.paid_purchase_volume_30d)}
              />
              <AdminSnapshotStat
                label={t('overview.billing.failed30d')}
                value={formatInteger(data.billing.failed_purchases_30d, i18n.language)}
              />
            </AdminSnapshotCard>

            <AdminSnapshotCard
              icon={AppWindow}
              title={t('overview.sections.apps')}
              tone="info"
              testId="overview-apps-card"
            >
              <AdminSnapshotStat
                label={t('overview.apps.published')}
                value={formatInteger(data.apps.published, i18n.language)}
              />
              <AdminSnapshotStat
                label={t('overview.apps.installations')}
                value={formatInteger(data.apps.installations, i18n.language)}
              />
              <AdminSnapshotStat
                label={t('overview.apps.activeSubscriptions')}
                value={formatInteger(data.apps.active_subscriptions, i18n.language)}
              />
              <AdminSnapshotStat
                label={t('overview.apps.activeLicenses')}
                value={formatInteger(data.apps.active_licenses, i18n.language)}
              />
            </AdminSnapshotCard>
          </section>

          <Card className="shadow-xs" data-testid="overview-gateway-card">
            <CardHeader className="space-y-0 px-5 pt-5 pb-4 sm:px-6">
              <AdminCardHeader
                icon={CreditCard}
                tone="neutral"
                title={t('overview.sections.gateway')}
                description={
                  data.gateway
                    ? t('overview.gateway.activeHint', {
                        code: data.gateway.code,
                        defaultValue: `Enabled gateway: ${data.gateway.code}`,
                      })
                    : t('overview.gateway.none')
                }
              />
            </CardHeader>
            <CardContent className="px-5 pb-5 sm:px-6 sm:pb-6">
              {data.gateway ? (
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="text-lg font-semibold tabular-nums">{data.gateway.code}</span>
                  <Badge appearance="light">
                    {data.gateway.enabled
                      ? t('paymentGateways.active')
                      : t('paymentGateways.inactive')}
                  </Badge>
                  {data.gateway.test_mode ? (
                    <Badge variant="outline">{t('overview.gateway.testMode')}</Badge>
                  ) : null}
                  <Link
                    to="/payment-gateways"
                    className="ms-auto inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    {t('overview.gateway.manage')}
                    <ChevronRight className="size-4 rtl:rotate-180" aria-hidden />
                  </Link>
                </div>
              ) : (
                <Link
                  to="/payment-gateways"
                  className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                >
                  {t('overview.gateway.manage')}
                  <ChevronRight className="size-4 rtl:rotate-180" aria-hidden />
                </Link>
              )}
            </CardContent>
          </Card>

          <Card className="shadow-xs" data-testid="overview-activity-card">
            <CardHeader className="space-y-0 px-5 pt-5 pb-4 sm:px-6">
              <AdminCardHeader
                icon={ScrollText}
                tone="neutral"
                title={t('overview.sections.activity')}
                description={t('overview.sections.activityHint')}
                trailing={
                  <Link
                    to="/audit-logs"
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    {t('overview.activity.viewAll')}
                    <ChevronRight className="size-4 rtl:rotate-180" aria-hidden />
                  </Link>
                }
              />
            </CardHeader>
            <CardContent className="space-y-2 px-5 pb-5 sm:px-6 sm:pb-6">
              {data.recent_activity.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground">
                  {t('overview.activity.empty')}
                </p>
              ) : (
                data.recent_activity.map((item) => (
                  <div
                    key={item.id}
                    className="flex flex-col gap-2 rounded-xl border border-border/70 bg-muted/15 px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-snug">
                        {item.summary ?? item.action}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {item.actor?.email ?? t('overview.activity.systemActor')} ·{' '}
                        {item.workspace?.name ?? t('overview.activity.platformScope')}
                      </p>
                    </div>
                    <p className="shrink-0 text-xs tabular-nums text-muted-foreground">
                      {formatAdminDateTime(item.created_at, i18n.language)}
                    </p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
