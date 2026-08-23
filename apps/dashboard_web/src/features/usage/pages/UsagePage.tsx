import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Activity, ChevronRight, RefreshCw } from 'lucide-react';
import { SimpleLineChart } from '@/components/charts/SimpleLineChart';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { formatInteger, formatTokens } from '@/lib/format';
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
          >
            <RefreshCw className="size-4" aria-hidden />
            {t('common.refresh')}
          </Button>
        </div>
      </header>

      {(summaryQuery.isLoading || trendQuery.isLoading) && (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      )}
      {(summaryQuery.isError || trendQuery.isError) && (
        <p className="text-sm text-destructive">
          {getErrorMessage(summaryQuery.error ?? trendQuery.error, t)}
        </p>
      )}

      {summaryQuery.data ? (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t('usage.summary.total')}</CardDescription>
              <CardTitle className="text-2xl">
                {formatTokens(summaryQuery.data.total_billed_tokens, i18n.language)}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t('usage.summary.activeWorkspaces')}</CardDescription>
              <CardTitle className="text-2xl">
                {formatInteger(summaryQuery.data.active_workspaces, i18n.language)}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t('usage.summary.averageDaily')}</CardDescription>
              <CardTitle className="text-2xl">
                {formatTokens(summaryQuery.data.average_daily_billed_tokens, i18n.language)}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>{t('usage.summary.range')}</CardDescription>
              <CardTitle className="text-base font-medium">
                {formatAdminDate(summaryQuery.data.from_day, i18n.language)} –{' '}
                {formatAdminDate(summaryQuery.data.to_day, i18n.language)}
              </CardTitle>
            </CardHeader>
          </Card>
        </section>
      ) : null}

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
