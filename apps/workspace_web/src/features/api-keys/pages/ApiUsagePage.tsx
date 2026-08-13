import { useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertTriangle, ChevronRight, Gauge, KeyRound, RefreshCw, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { InfoTooltip } from '@/components/shared/InfoTooltip';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { QuotaMeter } from '@/features/usage/components/QuotaMeter';
import {
  formatCount,
  formatPeriodDateTime,
  formatRelativeTime,
} from '@/features/usage/lib/quota';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { cn } from '@/lib/utils';
import { API_USAGE_HISTORY_PAGE_SIZE } from '@/services/api/api-keys';
import { ApiUsageHistoryList } from '../components/ApiUsageHistoryList';
import { ApiUsageKeyList } from '../components/ApiUsageKeyList';
import { ApiUsagePeriodTabs } from '../components/ApiUsagePeriodTabs';
import { useApiUsageHistory, useApiUsageSummary } from '../hooks/useApiKeyQueries';
import { apiUsageHref, parseApiUsagePage, parseApiUsagePeriod } from '../lib/period';

function UsageSkeleton() {
  return (
    <div className="space-y-6" data-testid="api-usage-loading">
      <div className="grid gap-5 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="shadow-xs">
            <CardContent className="p-6 space-y-5">
              <div className="h-4 w-1/2 rounded bg-muted animate-pulse" />
              <div className="h-8 w-1/3 rounded bg-muted animate-pulse" />
              <div className="h-2 w-full rounded bg-muted animate-pulse" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="shadow-xs">
        <CardContent className="p-5 space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 rounded bg-muted animate-pulse" />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export function ApiUsagePage() {
  const { t, i18n } = useTranslation();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const [params, setSearchParams] = useSearchParams();
  const period = parseApiUsagePeriod(params.get('period'));
  const keyFilter = params.get('key');
  const page = parseApiUsagePage(params.get('page'));
  const offset = (page - 1) * API_USAGE_HISTORY_PAGE_SIZE;

  const previousWorkspaceId = useRef(workspaceId);
  useEffect(() => {
    if (previousWorkspaceId.current === workspaceId) return;
    previousWorkspaceId.current = workspaceId;
    if (!params.get('key') && !params.get('page')) return;
    const next = new URLSearchParams(params);
    next.delete('key');
    next.delete('page');
    setSearchParams(next, { replace: true });
    // Drop the previous Workspace's key filter on switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const summaryQuery = useApiUsageSummary(period);
  const historyQuery = useApiUsageHistory({
    limit: API_USAGE_HISTORY_PAGE_SIZE,
    offset,
    period,
    api_key_id: keyFilter || undefined,
  });

  const summary = summaryQuery.data;
  const loading = summaryQuery.isLoading;
  const error = summaryQuery.isError;
  const rate = summary?.rate_limit.requests_per_minute ?? null;
  const monthly = summary?.workspace_ai_monthly;
  const keys = summary?.keys ?? [];
  const history = historyQuery.data;
  const items = history?.items ?? [];
  const total = history?.total ?? 0;
  const selectedKey = keyFilter
    ? keys.find((key) => key.api_key_id === keyFilter)
    : undefined;
  const periodFrom = formatPeriodDateTime(summary?.period.from_at ?? null, i18n.language);
  const periodTo = formatPeriodDateTime(summary?.period.to_at ?? null, i18n.language);
  const updatedLabel =
    summaryQuery.dataUpdatedAt > 0
      ? formatRelativeTime(
          new Date(summaryQuery.dataUpdatedAt).toISOString(),
          i18n.language,
        )
      : null;

  function retry() {
    void summaryQuery.refetch();
    void historyQuery.refetch();
  }

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('apiUsage.title')} />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t('apiUsage.eyebrow')}
          </p>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
            {t('apiUsage.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            {t('apiUsage.description')}
          </p>
          {periodFrom && periodTo && !loading ? (
            <p className="text-xs text-muted-foreground tabular-nums pt-1">
              {t('apiUsage.periodRange', { from: periodFrom, to: periodTo })}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-stretch gap-3 sm:items-end shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            {updatedLabel && !loading ? (
              <p className="text-xs text-muted-foreground hidden sm:block me-1">
                {t('apiUsage.updatedAt', { time: updatedLabel })}
              </p>
            ) : null}
            <Button variant="outline" size="sm" asChild>
              <Link to="/api/keys">
                <KeyRound className="size-3.5" />
                {t('apiUsage.manageKeys')}
              </Link>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={retry}
              disabled={summaryQuery.isFetching}
            >
              <RefreshCw
                className={cn('size-3.5', summaryQuery.isFetching && 'animate-spin')}
              />
              {t('apiUsage.refresh')}
            </Button>
          </div>
          <ApiUsagePeriodTabs period={period} keyFilter={keyFilter} />
        </div>
      </div>

      {loading ? <UsageSkeleton /> : null}

      {error && !loading ? (
        <Card className="shadow-xs" data-testid="api-usage-error">
          <CardHeader>
            <CardTitle>{t('apiUsage.loadError')}</CardTitle>
            <CardDescription>{t('apiUsage.loadErrorHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={retry}>
              {t('apiUsage.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!loading && !error && summary ? (
        <>
          <div className="grid gap-5 lg:grid-cols-3 lg:items-stretch">
            <Card className="shadow-xs overflow-hidden" data-testid="api-usage-rate-limit">
              <CardHeader className="min-h-14 px-6">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="size-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                    <Gauge className="size-4" aria-hidden />
                  </div>
                  <CardTitle className="flex items-center gap-1.5 min-w-0">
                    <span className="truncate">{t('apiUsage.rateLimitTitle')}</span>
                    <InfoTooltip
                      label={t('apiUsage.rateLimitTitle')}
                      content={`${t('apiUsage.rateLimitHint')} ${t('apiUsage.noRequestCounterHint')}`}
                    />
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="p-6">
                {rate === 0 ? (
                  <div
                    role="alert"
                    className="rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3.5 text-sm text-destructive flex items-start gap-3"
                  >
                    <AlertTriangle className="size-4 shrink-0 mt-0.5" aria-hidden />
                    <p className="leading-relaxed">{t('apiUsage.rateLimitDisabled')}</p>
                  </div>
                ) : (
                  <p className="text-3xl font-semibold tabular-nums tracking-tight leading-none">
                    {t('apiUsage.requestsPerMinute', {
                      value: formatCount(rate ?? 0, i18n.language),
                    })}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card className="shadow-xs overflow-hidden" data-testid="api-usage-ai-tokens">
              <CardHeader className="min-h-14 px-6">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="size-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                    <Sparkles className="size-4" aria-hidden />
                  </div>
                  <CardTitle className="flex items-center gap-1.5 min-w-0">
                    <span className="truncate">{t('apiUsage.aiTitle')}</span>
                    <InfoTooltip
                      label={t('apiUsage.aiTitle')}
                      content={t('apiUsage.aiHint')}
                    />
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="p-6 space-y-5">
                <div className="space-y-2">
                  <p className="text-3xl font-semibold tabular-nums tracking-tight leading-none">
                    {formatCount(summary.ai_tokens.billed, i18n.language)}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {t('apiUsage.billedCaption')}
                  </p>
                </div>
                <Button variant="outline" size="sm" asChild>
                  <Link to="/billing/usage" data-testid="api-usage-full-usage">
                    {t('apiUsage.viewFullUsage')}
                    <ChevronRight className="size-3.5 rtl:rotate-180" aria-hidden />
                  </Link>
                </Button>
              </CardContent>
            </Card>

            {monthly ? (
              <QuotaMeter
                title={t('apiUsage.monthlyPoolTitle')}
                meter={monthly}
                testId="api-usage-monthly-pool"
                format="tokens"
                icon={Sparkles}
              />
            ) : null}
          </div>

          <Card className="shadow-xs">
            <CardHeader>
              <CardHeading>
                <CardTitle>{t('apiUsage.byKeyTitle')}</CardTitle>
                <CardDescription>{t('apiUsage.byKeyHint')}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent>
              <ApiUsageKeyList
                keys={keys}
                period={period}
                keyFilter={keyFilter}
                billedTotal={summary.ai_tokens.billed}
              />
            </CardContent>
          </Card>

          <Card className="shadow-xs overflow-hidden">
            <CardHeader>
              <CardHeading>
                <CardTitle>{t('apiUsage.recentTitle')}</CardTitle>
                <CardDescription>
                  {selectedKey
                    ? t('apiUsage.recentHintFiltered', {
                        name: selectedKey.name || selectedKey.prefix,
                      })
                    : t('apiUsage.recentHint')}
                </CardDescription>
              </CardHeading>
              {selectedKey ? (
                <CardToolbar>
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={apiUsageHref(period, null, 1)}>{t('apiUsage.clearFilter')}</Link>
                  </Button>
                </CardToolbar>
              ) : null}
            </CardHeader>
            <CardContent className="p-0">
              <ApiUsageHistoryList
                items={items}
                loading={historyQuery.isLoading}
                period={period}
                keyFilter={keyFilter}
                page={page}
                total={total}
                pageSize={API_USAGE_HISTORY_PAGE_SIZE}
              />
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
