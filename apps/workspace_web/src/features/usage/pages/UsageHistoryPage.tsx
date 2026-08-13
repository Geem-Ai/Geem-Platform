import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowUpFromLine,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { UsageHistoryTokens } from '@/services/api/usage';
import { isAiHistoryKind, USAGE_HISTORY_PAGE_SIZE } from '@/services/api/usage';
import { UsageHistoryList } from '../components/UsageHistoryList';
import { UsageHistoryPagination } from '../components/UsageHistoryPagination';
import { useUsageHistory } from '../hooks/useUsageQueries';
import {
  HISTORY_DATE_PRESETS,
  HISTORY_KIND_FILTERS,
  historyPageHref,
  matchDatePreset,
  parseDateKey,
  parseHistoryKind,
  presetDateRange,
  type HistoryDatePreset,
  type HistoryDateRange,
  type HistoryKindFilter,
} from '../lib/history';
import { formatCount, formatRelativeTime } from '../lib/quota';

function parsePage(raw: string | null): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.floor(n);
}

function HistorySkeleton() {
  return (
    <div className="space-y-0" data-testid="usage-history-loading">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-5 py-3.5 border-t first:border-t-0 border-border"
        >
          <div className="size-8 rounded-lg bg-muted animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-40 rounded bg-muted animate-pulse" />
            <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          </div>
          <div className="h-3.5 w-20 rounded bg-muted animate-pulse" />
        </div>
      ))}
    </div>
  );
}

function filterLabelKey(kind: HistoryKindFilter): string {
  if (kind === 'ai') return 'usage.historyFilterAi';
  if (kind === 'credits') return 'usage.historyFilterCredits';
  return 'usage.historyFilterAll';
}

function datePresetLabelKey(preset: Exclude<HistoryDatePreset, 'custom'>): string {
  if (preset === 'today') return 'usage.historyToday';
  if (preset === '7d') return 'usage.historyLast7Days';
  if (preset === '30d') return 'usage.historyLast30Days';
  return 'usage.historyAllTime';
}

function TokenStatCard({
  testId,
  label,
  value,
  icon: Icon,
}: {
  testId: string;
  label: string;
  value: string;
  icon: typeof Sparkles;
}) {
  return (
    <Card className="shadow-xs" data-testid={testId}>
      <CardContent className="p-5 flex items-start gap-3">
        <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
          <Icon className="size-3.5" aria-hidden />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tabular-nums tracking-tight mt-1">
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function UsageHistoryPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const page = parsePage(searchParams.get('page'));
  const kind = parseHistoryKind(searchParams.get('kind'));
  const dates: HistoryDateRange = {
    from: parseDateKey(searchParams.get('from')),
    to: parseDateKey(searchParams.get('to')),
  };
  const datePreset = matchDatePreset(dates);
  const offset = (page - 1) * USAGE_HISTORY_PAGE_SIZE;
  const historyQuery = useUsageHistory({
    limit: USAGE_HISTORY_PAGE_SIZE,
    offset,
    kind,
    from: dates.from,
    to: dates.to,
  });

  const items = historyQuery.data?.items ?? [];
  const total = historyQuery.data?.total ?? items.length;
  const counts = historyQuery.data?.counts ?? {
    all: total,
    ai: items.filter((row) => isAiHistoryKind(row.kind)).length,
    credits: items.filter((row) => !isAiHistoryKind(row.kind)).length,
  };
  const tokens: UsageHistoryTokens = historyQuery.data?.tokens ?? {
    input: 0,
    output: 0,
    total: 0,
  };
  const updatedLabel =
    historyQuery.dataUpdatedAt > 0
      ? formatRelativeTime(
          new Date(historyQuery.dataUpdatedAt).toISOString(),
          i18n.language,
        )
      : null;
  const emptyHint =
    kind === 'all' && !dates.from && !dates.to
      ? t('usage.historyEmptyHint')
      : t('usage.historyEmptyFiltered');

  function go(nextPage: number, nextKind: HistoryKindFilter, nextDates: HistoryDateRange) {
    navigate(historyPageHref(nextPage, nextKind, nextDates));
  }

  function onCustomDate(field: 'from' | 'to', value: string) {
    const parsed = parseDateKey(value);
    const next: HistoryDateRange = { ...dates, [field]: parsed };
    if (next.from && next.to && next.from > next.to) {
      if (field === 'from') next.to = next.from;
      else next.from = next.to;
    }
    go(1, kind, next);
  }

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-6 ms-auto me-auto">
      <DocumentTitle title={t('usage.historyPageTitle')} />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-3">
          <nav
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
            aria-label={t('usage.historyBreadcrumb')}
          >
            <span>{t('usage.eyebrow')}</span>
            <span aria-hidden>/</span>
            <Link to="/billing/usage" className="hover:text-foreground hover:underline underline-offset-2">
              {t('usage.title')}
            </Link>
            <span aria-hidden>/</span>
            <span className="text-foreground">{t('usage.history')}</span>
          </nav>
          <div className="space-y-1">
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
              {t('usage.historyPageTitle')}
            </h1>
            <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
              {t('usage.historyPageDescription')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 self-start">
          {updatedLabel && !historyQuery.isLoading ? (
            <p className="text-xs text-muted-foreground hidden sm:block">
              {t('usage.updatedAt', { time: updatedLabel })}
            </p>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void historyQuery.refetch()}
            disabled={historyQuery.isFetching}
          >
            <RefreshCw
              className={cn('size-3.5', historyQuery.isFetching && 'animate-spin')}
              aria-hidden
            />
            {t('usage.refresh')}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div
          className="inline-flex flex-wrap items-center gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5"
          role="tablist"
          aria-label={t('usage.historyFilter')}
          data-testid="usage-history-filters"
        >
          {HISTORY_KIND_FILTERS.map((filter) => {
            const active = filter === kind;
            const count =
              filter === 'ai' ? counts.ai : filter === 'credits' ? counts.credits : counts.all;
            return (
              <Button
                key={filter}
                variant="ghost"
                size="sm"
                asChild
                className={cn(
                  'rounded-md',
                  active
                    ? 'bg-background text-foreground shadow-xs hover:bg-background'
                    : 'text-muted-foreground',
                )}
              >
                <Link
                  to={historyPageHref(1, filter, dates)}
                  role="tab"
                  aria-selected={active}
                  data-testid={`usage-history-filter-${filter}`}
                >
                  {t(filterLabelKey(filter))}
                  <span className="tabular-nums text-[11px] text-muted-foreground">
                    {formatCount(count, i18n.language)}
                  </span>
                </Link>
              </Button>
            );
          })}
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          <div
            className="inline-flex flex-wrap items-center gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5"
            role="tablist"
            aria-label={t('usage.historyDateFilter')}
            data-testid="usage-history-date-presets"
          >
            {HISTORY_DATE_PRESETS.map((preset) => {
              const active = datePreset === preset;
              return (
                <Button
                  key={preset}
                  variant="ghost"
                  size="sm"
                  asChild
                  className={cn(
                    'rounded-md',
                    active
                      ? 'bg-background text-foreground shadow-xs hover:bg-background'
                      : 'text-muted-foreground',
                  )}
                >
                  <Link
                    to={historyPageHref(1, kind, presetDateRange(preset))}
                    role="tab"
                    aria-selected={active}
                    data-testid={`usage-history-date-${preset}`}
                  >
                    {t(datePresetLabelKey(preset))}
                  </Link>
                </Button>
              );
            })}
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground whitespace-nowrap" htmlFor="history-from">
              {t('usage.historyFrom')}
            </label>
            <Input
              id="history-from"
              type="date"
              variant="sm"
              className="w-[9.5rem]"
              value={dates.from ?? ''}
              onChange={(event) => onCustomDate('from', event.target.value)}
              data-testid="usage-history-from"
            />
            <label className="text-xs text-muted-foreground whitespace-nowrap" htmlFor="history-to">
              {t('usage.historyTo')}
            </label>
            <Input
              id="history-to"
              type="date"
              variant="sm"
              className="w-[9.5rem]"
              value={dates.to ?? ''}
              onChange={(event) => onCustomDate('to', event.target.value)}
              data-testid="usage-history-to"
            />
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <TokenStatCard
          testId="usage-history-tokens-in"
          label={t('usage.historyTokensIn')}
          value={formatCount(tokens.input, i18n.language)}
          icon={ArrowDownToLine}
        />
        <TokenStatCard
          testId="usage-history-tokens-out"
          label={t('usage.historyTokensOut')}
          value={formatCount(tokens.output, i18n.language)}
          icon={ArrowUpFromLine}
        />
        <TokenStatCard
          testId="usage-history-tokens-total"
          label={t('usage.historyTokensTotal')}
          value={formatCount(tokens.total, i18n.language)}
          icon={Sparkles}
        />
      </div>

      <Card className="shadow-xs overflow-hidden">
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('usage.historyLogTitle')}</CardTitle>
            <CardDescription>{t('usage.historyLogDescription')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/billing/usage" data-testid="usage-history-back">
                <ArrowLeft className="size-3.5 rtl:rotate-180" aria-hidden />
                {t('usage.historyBack')}
              </Link>
            </Button>
          </CardToolbar>
        </CardHeader>
        <CardContent className="p-0">
          {historyQuery.isLoading && !historyQuery.data ? (
            <HistorySkeleton />
          ) : historyQuery.isError ? (
            <div className="space-y-3 px-5 py-8" data-testid="usage-history-error">
              <p className="text-sm text-destructive">{t('usage.historyError')}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void historyQuery.refetch()}
              >
                {t('usage.retry')}
              </Button>
            </div>
          ) : (
            <UsageHistoryList
              items={items}
              variant="ledger"
              emptyHint={emptyHint}
              hideKindTitle={kind === 'credits'}
            />
          )}
        </CardContent>
        {!historyQuery.isError && total > 0 ? (
          <CardFooter className="w-full">
            <UsageHistoryPagination
              page={page}
              pageSize={USAGE_HISTORY_PAGE_SIZE}
              total={total}
              kind={kind}
              dates={dates}
            />
          </CardFooter>
        ) : null}
      </Card>
    </div>
  );
}
