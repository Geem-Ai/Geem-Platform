import { Link } from 'react-router-dom';
import {
  CalendarDays,
  ChevronRight,
  Coins,
  HardDrive,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
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
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import type { Meter } from '@/services/api/usage';
import { QuotaAlert } from '../components/QuotaAlert';
import { QuotaMeter } from '../components/QuotaMeter';
import { UsageHistoryList } from '../components/UsageHistoryList';
import {
  useSubscription,
  useUsageHistory,
  useUsageSummary,
} from '../hooks/useUsageQueries';
import {
  formatCount,
  formatPeriodDate,
  formatRelativeTime,
  meterWarningLevel,
  worstWarningLevel,
  type QuotaWarningLevel,
} from '../lib/quota';

function UsagePageSkeleton() {
  return (
    <div className="space-y-6" data-testid="usage-loading">
      <Card className="shadow-xs">
        <CardContent className="p-6 space-y-3">
          <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          <div className="h-7 w-48 rounded bg-muted animate-pulse" />
          <div className="h-3 w-64 rounded bg-muted animate-pulse" />
        </CardContent>
      </Card>
      <Card className="shadow-xs">
        <CardContent className="p-0">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="px-5 py-4 space-y-3 border-t first:border-t-0 border-border">
              <div className="h-4 w-40 rounded bg-muted animate-pulse" />
              <div className="h-1.5 w-full rounded bg-muted animate-pulse" />
            </div>
          ))}
        </CardContent>
      </Card>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="shadow-xs">
            <CardContent className="p-5 space-y-3">
              <div className="h-4 w-1/2 rounded bg-muted animate-pulse" />
              <div className="h-7 w-1/3 rounded bg-muted animate-pulse" />
              <div className="h-2 w-full rounded bg-muted animate-pulse" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function planStatusVariant(
  status: string,
): 'success' | 'warning' | 'secondary' {
  if (status === 'active' || status === 'trialing') return 'success';
  if (status === 'past_due') return 'warning';
  return 'secondary';
}

function healthCopyKey(level: QuotaWarningLevel): string | null {
  if (level === 'exhausted') return 'usage.healthExhausted';
  if (level === 'critical') return 'usage.healthCritical';
  if (level === 'approaching') return 'usage.healthApproaching';
  return null;
}

export function UsagePage() {
  const { t, i18n } = useTranslation();
  const summaryQuery = useUsageSummary();
  const historyQuery = useUsageHistory();
  const subscriptionQuery = useSubscription();

  const summary = summaryQuery.data;
  const subscription = subscriptionQuery.data;
  const loading = summaryQuery.isLoading || subscriptionQuery.isLoading;
  const error = summaryQuery.isError || subscriptionQuery.isError;

  function retry() {
    void summaryQuery.refetch();
    void historyQuery.refetch();
    void subscriptionQuery.refetch();
  }

  const planStatusKey = subscription
    ? `usage.subscriptionStatus.${subscription.status}`
    : null;
  const planStatusLabel =
    planStatusKey && i18n.exists(planStatusKey)
      ? t(planStatusKey)
      : (subscription?.status ?? '');

  const storageMeter: Meter | null = summary
    ? {
        limit: summary.storage.limit_bytes,
        used: summary.storage.used_bytes,
        reserved: summary.storage.reserved_bytes,
        remaining: summary.storage.remaining_bytes,
        period_start: summary.storage_bytes.period_start,
        period_end: summary.storage_bytes.period_end,
      }
    : null;

  const healthLevel = summary
    ? worstWarningLevel([
        meterWarningLevel(summary.ai.daily),
        meterWarningLevel(summary.ai.weekly),
        meterWarningLevel(summary.ai.monthly),
        meterWarningLevel(summary.experts),
        meterWarningLevel(storageMeter!),
      ])
    : 'normal';
  const healthKey = healthCopyKey(healthLevel);

  const periodStart = subscription
    ? formatPeriodDate(subscription.current_period_start, i18n.language)
    : null;
  const periodEnd = subscription
    ? formatPeriodDate(subscription.current_period_end, i18n.language)
    : null;
  const updatedLabel =
    summaryQuery.dataUpdatedAt > 0
      ? formatRelativeTime(
          new Date(summaryQuery.dataUpdatedAt).toISOString(),
          i18n.language,
        )
      : null;

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('usage.title')} />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t('usage.eyebrow')}
          </p>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
            {t('usage.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            {t('usage.description')}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 self-start">
          {updatedLabel && !loading ? (
            <p className="text-xs text-muted-foreground hidden sm:block">
              {t('usage.updatedAt', { time: updatedLabel })}
            </p>
          ) : null}
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
            {t('usage.refresh')}
          </Button>
        </div>
      </div>

      {loading ? <UsagePageSkeleton /> : null}

      {error && !loading ? (
        <Card data-testid="usage-error" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('usage.loadError')}</CardTitle>
            <CardDescription>{t('usage.loadErrorHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={retry}>
              {t('usage.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!loading && !error && summary ? (
        <>
          {healthKey ? (
            <QuotaAlert
              level={healthLevel}
              title={t(`usage.warning.${healthLevel}`)}
              description={t(healthKey)}
              showUsageLink={false}
            />
          ) : null}

          {subscription ? (
            <Card
              data-testid="usage-subscription"
              className="shadow-xs overflow-hidden"
            >
              <div className="h-0.5 bg-primary" aria-hidden />
              <CardContent className="p-5 sm:p-6">
                <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                  <div className="min-w-0 space-y-2">
                    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {t('usage.subscription')}
                    </p>
                    <div className="flex flex-wrap items-center gap-2.5">
                      <h2
                        className="text-xl font-semibold tracking-tight"
                        data-testid="usage-plan-name"
                      >
                        {subscription.plan.name}
                      </h2>
                      <Badge
                        variant={planStatusVariant(subscription.status)}
                        appearance="light"
                        size="sm"
                      >
                        {planStatusLabel}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground max-w-xl leading-relaxed">
                      {t('usage.subscriptionReadOnly')}
                    </p>
                  </div>
                  {periodStart && periodEnd ? (
                    <div className="text-sm lg:text-end">
                      <p className="text-xs text-muted-foreground mb-1">
                        {t('usage.currentPeriod')}
                      </p>
                      <p className="font-medium tabular-nums">
                        {t('usage.planPeriod', { start: periodStart, end: periodEnd })}
                      </p>
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card className="shadow-xs overflow-hidden">
            <CardHeader className="min-h-14">
              <CardHeading>
                <div className="flex items-center gap-2.5">
                  <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                    <Sparkles className="size-3.5" aria-hidden />
                  </div>
                  <div>
                    <CardTitle>{t('usage.aiTitle')}</CardTitle>
                    <CardDescription className="mt-1">
                      {t('usage.aiDescription')}
                    </CardDescription>
                  </div>
                </div>
              </CardHeading>
            </CardHeader>
            <CardContent className="p-0">
              <QuotaMeter
                title={t('usage.daily')}
                meter={summary.ai.daily}
                testId="usage-ai-daily"
                format="tokens"
                layout="row"
                icon={CalendarDays}
              />
              <Separator />
              <QuotaMeter
                title={t('usage.weekly')}
                meter={summary.ai.weekly}
                testId="usage-ai-weekly"
                format="tokens"
                layout="row"
                icon={CalendarDays}
              />
              <Separator />
              <QuotaMeter
                title={t('usage.monthly')}
                meter={summary.ai.monthly}
                testId="usage-ai-monthly"
                format="tokens"
                layout="row"
                icon={CalendarDays}
              />
            </CardContent>
          </Card>

          <section className="space-y-3">
            <div>
              <h2 className="text-sm font-semibold tracking-tight">
                {t('usage.capacityTitle')}
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                {t('usage.capacityDescription')}
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <QuotaMeter
                title={t('usage.experts')}
                meter={summary.experts}
                testId="usage-experts"
                icon={Sparkles}
              />
              <QuotaMeter
                title={t('usage.storage')}
                meter={storageMeter!}
                testId="usage-storage"
                format="bytes"
                icon={HardDrive}
              />
              <Card data-testid="usage-credits" className="shadow-xs">
                <CardHeader className="min-h-14">
                  <div className="flex items-center gap-2.5">
                    <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <Coins className="size-3.5" aria-hidden />
                    </div>
                    <CardTitle className="text-sm">{t('usage.credits')}</CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div>
                    <p className="text-xs text-muted-foreground">{t('usage.creditsBalance')}</p>
                    <p
                      className="text-2xl font-semibold tabular-nums tracking-tight mt-1"
                      data-testid="usage-credits-balance"
                    >
                      {formatCount(summary.credits.balance, i18n.language)}
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {t('usage.creditsHint')}
                  </p>
                </CardContent>
              </Card>
            </div>
          </section>

          <Card className="shadow-xs">
            <CardHeader>
              <CardHeading>
                <CardTitle>{t('usage.history')}</CardTitle>
                <CardDescription>{t('usage.historyDescription')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <Button variant="ghost" size="sm" asChild>
                  <Link to="/billing/usage/history" data-testid="usage-history-view-all">
                    {t('usage.historyViewAll')}
                    <ChevronRight className="size-3.5 rtl:rotate-180" aria-hidden />
                  </Link>
                </Button>
              </CardToolbar>
            </CardHeader>
            <CardContent>
              {historyQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>
              ) : historyQuery.isError ? (
                <p className="text-sm text-destructive">{t('usage.historyError')}</p>
              ) : (
                <UsageHistoryList items={historyQuery.data?.items ?? []} />
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
