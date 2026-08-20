import { useEffect, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  ArrowUpDown,
  CircleAlert,
  Coins,
  ExternalLink,
  History,
  Layers3,
  RefreshCw,
  SearchX,
  type LucideIcon,
} from 'lucide-react';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import {
  WorkspaceKindBadge,
  WorkspaceStatusBadge,
} from '@/components/shared/StatusBadges';
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
import { CreditLedgerRow } from '@/features/credits/components/CreditLedgerRow';
import { GrantCreditsDialog } from '@/features/credits/components/GrantCreditsDialog';
import {
  creditLedgerDelta,
  formatSignedCredits,
} from '@/features/credits/lib/ledger';
import { formatInteger } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformWorkspace,
  fetchWorkspaceCreditHistory,
  fetchWorkspaceCredits,
  platformQueryKeys,
} from '@/services/api/platform';

const HISTORY_PAGE_SIZE = 20;

export function CreditDetailPage() {
  const { workspaceId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [grantOpen, setGrantOpen] = useState(false);

  useEffect(() => {
    setHistoryOffset(0);
    setGrantOpen(false);
  }, [workspaceId]);

  const workspaceQuery = useQuery({
    queryKey: platformQueryKeys.workspace(workspaceId),
    queryFn: () => fetchPlatformWorkspace(workspaceId),
    enabled: Boolean(workspaceId),
  });

  const creditsQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCredits(workspaceId),
    queryFn: () => fetchWorkspaceCredits(workspaceId),
    enabled: Boolean(workspaceId),
  });

  const historyFilters = { limit: HISTORY_PAGE_SIZE, offset: historyOffset };
  const historyQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCreditHistory(workspaceId, historyFilters),
    queryFn: () => fetchWorkspaceCreditHistory(workspaceId, historyFilters),
    enabled: Boolean(workspaceId),
  });

  const refresh = async () => {
    await Promise.all([
      workspaceQuery.refetch(),
      creditsQuery.refetch(),
      historyQuery.refetch(),
    ]);
  };

  const onGranted = async () => {
    setHistoryOffset(0);
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: platformQueryKeys.workspaceCredits(workspaceId),
      }),
      queryClient.invalidateQueries({
        queryKey: ['platform', 'workspace', workspaceId, 'credits', 'history'],
      }),
    ]);
  };

  if (workspaceQuery.isLoading && !workspaceQuery.data) {
    return <CreditDetailSkeleton />;
  }

  if (!workspaceQuery.data) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8">
        <DocumentTitle title={t('credits.title')} />
        <BackToCredits />
        <Card data-testid="credit-detail-error">
          <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center" role="alert">
            <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <CircleAlert className="size-5" aria-hidden />
            </span>
            <h1 className="text-base font-semibold">{t('credits.detailErrorTitle')}</h1>
            <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
              {getErrorMessage(workspaceQuery.error, t)}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-5"
              onClick={() => void workspaceQuery.refetch()}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              {t('common.retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const workspace = workspaceQuery.data;
  const latestEntry = creditsQuery.data?.recent[0];
  const isSystem = workspace.kind === 'system';
  const isRefreshing =
    workspaceQuery.isFetching || creditsQuery.isFetching || historyQuery.isFetching;
  const canGrant = !isSystem && creditsQuery.isSuccess && !creditsQuery.isFetching;

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="credit-detail-page"
    >
      <DocumentTitle title={`${workspace.name} · ${t('credits.title')}`} />
      <BackToCredits />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-20 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-primary/15 bg-background/85 text-primary shadow-xs md:size-14">
              <Coins className="size-6" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
                {t('credits.eyebrow')}
              </p>
              <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight md:text-3xl">
                {workspace.name}
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                {t('credits.detailSubtitle')}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="min-w-0 max-w-full rounded-md border border-border bg-background/70 px-2 py-1 font-mono text-xs text-muted-foreground">
                  <bdi dir="ltr" className="break-all">
                    {workspace.slug}
                  </bdi>
                </span>
                <WorkspaceStatusBadge status={workspace.status} />
                <WorkspaceKindBadge kind={workspace.kind} />
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void refresh()}
              disabled={isRefreshing}
              data-testid="credit-detail-refresh"
              className="bg-background/80"
            >
              <RefreshCw className={cn('size-4', isRefreshing && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            <Button variant="outline" asChild className="bg-background/80">
              <Link to={`/workspaces/${workspace.id}`}>
                <ExternalLink className="size-4" aria-hidden />
                {t('credits.openWorkspace')}
              </Link>
            </Button>
            {!isSystem ? (
              <Button
                onClick={() => setGrantOpen(true)}
                disabled={!canGrant}
                data-testid="credit-detail-grant"
              >
                <Coins className="size-4" aria-hidden />
                {t('credits.grant')}
              </Button>
            ) : null}
          </div>
        </div>
      </section>

      {workspaceQuery.isError ? (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-destructive">
              {t('credits.detailErrorTitle')}
            </p>
            <p className="mt-1 break-words text-xs text-muted-foreground">
              {getErrorMessage(workspaceQuery.error, t)}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void workspaceQuery.refetch()}>
            <RefreshCw className="size-3.5" aria-hidden />
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      {creditsQuery.isError ? (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
          data-testid="credit-detail-balance-error"
        >
          <div>
            <p className="text-sm font-semibold text-destructive">
              {t('credits.balanceErrorTitle')}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {getErrorMessage(creditsQuery.error, t)}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void creditsQuery.refetch()}>
            <RefreshCw className="size-3.5" aria-hidden />
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('credits.accountSummary')}
        data-testid="credit-detail-summary"
      >
        <AccountMetric
          icon={Coins}
          label={t('credits.balance')}
          value={formatInteger(creditsQuery.data?.balance, i18n.language)}
          loading={creditsQuery.isLoading}
          tone="primary"
          ltr
          testId="credits-balance"
        />
        <AccountMetric
          icon={History}
          label={t('credits.stats.ledgerEntries')}
          value={formatInteger(historyQuery.data?.total, i18n.language)}
          loading={historyQuery.isLoading}
          tone="info"
          ltr
        />
        <AccountMetric
          icon={ArrowUpDown}
          label={t('credits.stats.latestMovement')}
          value={
            latestEntry
              ? formatSignedCredits(creditLedgerDelta(latestEntry), i18n.language)
              : t('common.none')
          }
          loading={creditsQuery.isLoading}
          tone={
            latestEntry && creditLedgerDelta(latestEntry) < 0 ? 'warning' : 'success'
          }
          ltr={Boolean(latestEntry)}
        />
        <AccountMetric
          icon={Layers3}
          label={t('credits.stats.currentPlan')}
          value={workspace.subscription?.plan_name ?? t('workspaces.noPlan')}
          loading={false}
          tone="neutral"
        />
      </section>

      <Card data-testid="credit-detail-history">
        <CardHeader className="py-4">
          <CardHeading>
            <CardTitle className="flex items-center gap-2">
              <History className="size-4 text-primary" aria-hidden />
              {t('credits.history')}
            </CardTitle>
            <CardDescription>{t('credits.historyDescription')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            {historyQuery.data ? (
              <Badge variant="secondary" appearance="light">
                {t('credits.entryCount', {
                  count: historyQuery.data.total,
                  formattedCount: historyQuery.data.total.toLocaleString(i18n.language),
                })}
              </Badge>
            ) : null}
          </CardToolbar>
        </CardHeader>
        <CardContent aria-busy={historyQuery.isLoading || historyQuery.isFetching}>
          {historyQuery.isLoading && !historyQuery.data ? <LedgerSkeleton /> : null}

          {historyQuery.isError && !historyQuery.data ? (
            <StatePanel
              icon={CircleAlert}
              title={t('credits.historyErrorTitle')}
              description={getErrorMessage(historyQuery.error, t)}
              action={
                <Button variant="outline" size="sm" onClick={() => void historyQuery.refetch()}>
                  <RefreshCw className="size-3.5" aria-hidden />
                  {t('common.retry')}
                </Button>
              }
              destructive
              testId="credit-detail-history-error"
            />
          ) : null}

          {historyQuery.data?.items.length === 0 ? (
            <StatePanel
              icon={SearchX}
              title={t('credits.historyEmptyTitle')}
              description={t('credits.historyEmpty')}
              testId="credit-detail-history-empty"
            />
          ) : null}

          {historyQuery.data && historyQuery.data.items.length > 0 ? (
            <div className="space-y-4">
              {historyQuery.isError ? (
                <div
                  className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
                  role="alert"
                >
                  <p className="min-w-0 break-words text-xs text-muted-foreground">
                    {getErrorMessage(historyQuery.error, t)}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void historyQuery.refetch()}
                  >
                    <RefreshCw className="size-3.5" aria-hidden />
                    {t('common.retry')}
                  </Button>
                </div>
              ) : null}
              <div
                className="overflow-hidden rounded-xl border border-border"
                data-testid="credit-detail-history-list"
              >
                <div className="hidden grid-cols-[minmax(100px,0.6fr)_minmax(180px,1.35fr)_minmax(95px,0.7fr)_minmax(80px,0.55fr)_minmax(115px,0.8fr)] gap-4 border-b border-border bg-muted/45 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground rtl:tracking-normal xl:grid">
                  <span>{t('credits.columns.type')}</span>
                  <span>{t('credits.columns.reason')}</span>
                  <span>{t('credits.columns.source')}</span>
                  <span>{t('credits.columns.change')}</span>
                  <span>{t('credits.columns.occurred')}</span>
                </div>
                <ul className="divide-y divide-border">
                  {historyQuery.data.items.map((entry) => (
                    <CreditLedgerRow
                      key={entry.id}
                      entry={entry}
                      locale={i18n.language}
                      tableBreakpoint="xl"
                    />
                  ))}
                </ul>
              </div>
              <AdminPagination
                total={historyQuery.data.total}
                limit={historyQuery.data.limit}
                offset={historyQuery.data.offset}
                onPageChange={setHistoryOffset}
                testId="credit-detail-history-pagination"
              />
            </div>
          ) : null}
        </CardContent>
      </Card>

      {!isSystem && creditsQuery.isSuccess ? (
        <GrantCreditsDialog
          open={grantOpen}
          onOpenChange={setGrantOpen}
          workspaceId={workspace.id}
          workspaceName={workspace.name}
          currentBalance={creditsQuery.data.balance}
          onGranted={onGranted}
        />
      ) : null}
    </div>
  );
}

function BackToCredits() {
  const { t } = useTranslation();

  return (
    <Link
      to="/credits"
      className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
      {t('credits.backToList')}
    </Link>
  );
}

type MetricTone = 'primary' | 'success' | 'warning' | 'info' | 'neutral';

function AccountMetric({
  icon: Icon,
  label,
  value,
  loading,
  tone,
  ltr = false,
  testId,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  loading: boolean;
  tone: MetricTone;
  ltr?: boolean;
  testId?: string;
}) {
  const tones: Record<MetricTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
    neutral: 'bg-muted text-muted-foreground',
  };

  return (
    <Card className="min-h-28" data-testid={testId}>
      <CardContent className="flex items-center justify-between gap-4 p-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? (
            <div className="mt-2 h-7 w-20 animate-pulse rounded bg-muted" />
          ) : (
            <p className="mt-1 truncate text-2xl font-semibold tabular-nums">
              {ltr ? <bdi dir="ltr">{value}</bdi> : value}
            </p>
          )}
        </div>
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tones[tone])}>
          <Icon className="size-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

function LedgerSkeleton() {
  const { t } = useTranslation();

  return (
    <div
      className="overflow-hidden rounded-xl border border-border"
      role="status"
      aria-label={t('common.loading')}
    >
      <div aria-hidden>
        <div className="h-10 animate-pulse border-b border-border bg-muted/50" />
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="flex items-center gap-4 border-b border-border p-4 last:border-0">
            <div className="h-5 w-20 animate-pulse rounded bg-muted" />
            <div className="h-3.5 flex-1 animate-pulse rounded bg-muted" />
            <div className="hidden h-3.5 w-24 animate-pulse rounded bg-muted sm:block" />
          </div>
        ))}
      </div>
    </div>
  );
}

function StatePanel({
  icon: Icon,
  title,
  description,
  action,
  destructive = false,
  testId,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  destructive?: boolean;
  testId: string;
}) {
  return (
    <div
      className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center"
      data-testid={testId}
      role={destructive ? 'alert' : undefined}
    >
      <span
        className={cn(
          'mb-4 flex size-11 items-center justify-center rounded-xl',
          destructive ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary',
        )}
      >
        <Icon className="size-5" aria-hidden />
      </span>
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

function CreditDetailSkeleton() {
  const { t } = useTranslation();

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="credit-detail-loading"
      role="status"
      aria-label={t('common.loading')}
    >
      <div className="h-5 w-32 animate-pulse rounded bg-muted" />
      <div className="h-52 animate-pulse rounded-2xl border border-border bg-muted/45" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-xl border border-border bg-muted/35" />
        ))}
      </div>
      <div className="h-80 animate-pulse rounded-xl border border-border bg-muted/35" />
    </div>
  );
}
