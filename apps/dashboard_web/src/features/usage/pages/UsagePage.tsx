import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  Building2,
  CalendarRange,
  ChevronRight,
  RefreshCw,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { SimpleLineChart } from '@/components/charts/SimpleLineChart';
import { AdminMetricCard } from '@/components/shared/AdminMetricCard';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { formatInteger, formatTokens } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformUsageSummary,
  fetchPlatformUsageTrend,
  fetchPlatformUsageWorkspaces,
  platformQueryKeys,
  usageDatePreset,
} from '@/services/api/platform';

const PAGE_SIZE = 10;
const PRESETS = [7, 30, 90] as const;

export function UsagePage() {
  const { t, i18n } = useTranslation();
  const [presetDays, setPresetDays] = useState<(typeof PRESETS)[number]>(30);
  const [offset, setOffset] = useState(0);
  const range = useMemo(() => usageDatePreset(presetDays), [presetDays]);

  const summaryQuery = useQuery({
    queryKey: platformQueryKeys.usageSummary(range),
    queryFn: () => fetchPlatformUsageSummary(range),
    staleTime: 60_000,
  });
  const trendQuery = useQuery({
    queryKey: platformQueryKeys.usageTrend(range),
    queryFn: () => fetchPlatformUsageTrend(range),
    staleTime: 60_000,
  });
  const workspacesQuery = useQuery({
    queryKey: platformQueryKeys.usageWorkspaces({ ...range, limit: PAGE_SIZE, offset }),
    queryFn: () => fetchPlatformUsageWorkspaces({ ...range, limit: PAGE_SIZE, offset }),
    staleTime: 60_000,
  });

  const chartPoints =
    trendQuery.data?.points.map((point) => ({ date: point.date, value: point.billed_tokens })) ?? [];

  const summary = summaryQuery.data;
  const rangeDayCount = useMemo(() => {
    if (!summary) return presetDays;
    const from = new Date(summary.from_day);
    const to = new Date(summary.to_day);
    const diff = Math.round((to.getTime() - from.getTime()) / 86_400_000);
    return diff + 1;
  }, [presetDays, summary]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6 md:p-8" data-testid="usage-page">
      <DocumentTitle title={t('usage.title')} />
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{t('usage.eyebrow')}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{t('usage.title')}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{t('usage.subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {PRESETS.map((days) => (
            <Button
              key={days}
              size="sm"
              variant={presetDays === days ? 'primary' : 'outline'}
              onClick={() => {
                setPresetDays(days);
                setOffset(0);
              }}
              data-testid={`usage-preset-${days}`}
            >
              {t('usage.presets.days', { count: days })}
            </Button>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void summaryQuery.refetch();
              void trendQuery.refetch();
              void workspacesQuery.refetch();
            }}
            disabled={summaryQuery.isFetching || trendQuery.isFetching}
          >
            <RefreshCw
              className={cn('size-4', (summaryQuery.isFetching || trendQuery.isFetching) && 'animate-spin')}
              aria-hidden
            />
            {t('common.refresh')}
          </Button>
        </div>
      </header>

      {(summaryQuery.isError || trendQuery.isError) && (
        <p className="text-sm text-destructive">
          {getErrorMessage(summaryQuery.error ?? trendQuery.error, t)}
        </p>
      )}

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('usage.summary.sectionLabel')}
        data-testid="usage-summary-metrics"
      >
        <AdminMetricCard
          icon={Zap}
          tone="primary"
          label={t('usage.summary.total')}
          value={summary ? formatTokens(summary.total_billed_tokens, i18n.language) : '—'}
          hint={
            summary?.peak_day
              ? t('usage.summary.totalHint', {
                  day: formatAdminDate(summary.peak_day.day, i18n.language),
                  tokens: formatTokens(summary.peak_day.billed_tokens, i18n.language),
                })
              : t('usage.summary.totalHintEmpty')
          }
          loading={summaryQuery.isLoading}
          testId="usage-metric-total"
        />
        <AdminMetricCard
          icon={Building2}
          tone="info"
          label={t('usage.summary.activeWorkspaces')}
          value={summary ? formatInteger(summary.active_workspaces, i18n.language) : '—'}
          hint={t('usage.summary.activeWorkspacesHint')}
          loading={summaryQuery.isLoading}
          testId="usage-metric-workspaces"
        />
        <AdminMetricCard
          icon={TrendingUp}
          tone="success"
          label={t('usage.summary.averageDaily')}
          value={summary ? formatTokens(summary.average_daily_billed_tokens, i18n.language) : '—'}
          hint={t('usage.summary.averageDailyHint', { days: rangeDayCount })}
          loading={summaryQuery.isLoading}
          testId="usage-metric-average"
        />
        <AdminMetricCard
          icon={CalendarRange}
          tone="neutral"
          label={t('usage.summary.range')}
          value={
            summary
              ? `${formatAdminDate(summary.from_day, i18n.language)} – ${formatAdminDate(summary.to_day, i18n.language)}`
              : '—'
          }
          hint={t('usage.summary.rangeHint', { count: presetDays })}
          loading={summaryQuery.isLoading}
          testId="usage-metric-range"
          compactValue
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="size-4" aria-hidden />
            {t('usage.trendTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SimpleLineChart
            points={chartPoints}
            locale={i18n.language}
            emptyLabel={t('usage.trendEmpty')}
            valueLabel={t('usage.trendTitle')}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('usage.topWorkspaces')}</CardTitle>
          <CardDescription>{t('usage.topWorkspacesHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {workspacesQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : null}
          {workspacesQuery.data?.items.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-border text-start text-muted-foreground">
                    <th className="px-2 py-2 font-medium">{t('usage.table.workspace')}</th>
                    <th className="px-2 py-2 font-medium">{t('usage.table.plan')}</th>
                    <th className="px-2 py-2 font-medium">{t('usage.table.billedTokens')}</th>
                    <th className="px-2 py-2 font-medium">{t('usage.table.share')}</th>
                    <th className="px-2 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {workspacesQuery.data.items.map((item) => (
                    <tr key={item.workspace_id} className="border-b border-border/70">
                      <td className="px-2 py-3">
                        <div className="font-medium">{item.workspace_name}</div>
                        <div className="text-xs text-muted-foreground">{item.workspace_slug}</div>
                      </td>
                      <td className="px-2 py-3">{item.current_plan_name ?? '—'}</td>
                      <td className="px-2 py-3">{formatTokens(item.billed_tokens, i18n.language)}</td>
                      <td className="px-2 py-3">{item.percentage_of_platform_usage.toFixed(1)}%</td>
                      <td className="px-2 py-3 text-end">
                        <Link
                          to={`/workspaces/${item.workspace_id}`}
                          className="inline-flex items-center gap-1 text-primary hover:underline"
                        >
                          {t('usage.viewWorkspace')}
                          <ChevronRight className="size-4 rtl:rotate-180" aria-hidden />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t('usage.topWorkspacesEmpty')}</p>
          )}
          <AdminPagination
            offset={offset}
            limit={PAGE_SIZE}
            total={workspacesQuery.data?.total ?? 0}
            onPageChange={setOffset}
          />
        </CardContent>
      </Card>
    </div>
  );
}
