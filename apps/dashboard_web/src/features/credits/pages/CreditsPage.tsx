import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  ArrowUpDown,
  Building2,
  Check,
  ChevronRight,
  CircleAlert,
  Coins,
  ExternalLink,
  History,
  Layers3,
  RefreshCw,
  SearchX,
  WalletCards,
  type LucideIcon,
} from 'lucide-react';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { WorkspaceStatusBadge } from '@/components/shared/StatusBadges';
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
import { GrantCreditsDialog } from '@/features/credits/components/GrantCreditsDialog';
import { CreditLedgerRow } from '@/features/credits/components/CreditLedgerRow';
import {
  creditLedgerDelta,
  formatSignedCredits,
} from '@/features/credits/lib/ledger';
import { formatInteger } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformWorkspaces,
  fetchWorkspaceCreditHistory,
  fetchWorkspaceCredits,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformWorkspaceListItem } from '@/services/api/types';

const PAGE_SIZE = 25;
const HISTORY_PAGE_SIZE = 20;

export function CreditsPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [workspaceOffset, setWorkspaceOffset] = useState(0);
  const [selectedWorkspace, setSelectedWorkspace] =
    useState<PlatformWorkspaceListItem | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [grantOpen, setGrantOpen] = useState(false);

  const selectedId = selectedWorkspace?.id ?? null;
  const workspaceFilters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: workspaceOffset,
      search: search || undefined,
      status: status || undefined,
      kind: 'tenant',
    }),
    [search, status, workspaceOffset],
  );

  const workspacesQuery = useQuery({
    queryKey: platformQueryKeys.workspaces(workspaceFilters),
    queryFn: () => fetchPlatformWorkspaces(workspaceFilters),
  });

  const creditsQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCredits(selectedId ?? ''),
    queryFn: () => fetchWorkspaceCredits(selectedId!),
    enabled: Boolean(selectedId),
  });

  const historyFilters = useMemo(
    () => ({ limit: HISTORY_PAGE_SIZE, offset: historyOffset }),
    [historyOffset],
  );

  const historyQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCreditHistory(selectedId ?? '', historyFilters),
    queryFn: () => fetchWorkspaceCreditHistory(selectedId!, historyFilters),
    enabled: Boolean(selectedId),
  });

  const latestEntry = creditsQuery.data?.recent[0];
  const hasCustomFilters = Boolean(search || status);
  const isRefreshing =
    workspacesQuery.isFetching || creditsQuery.isFetching || historyQuery.isFetching;

  const clearSelection = () => {
    setSelectedWorkspace(null);
    setHistoryOffset(0);
    setGrantOpen(false);
  };

  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setWorkspaceOffset(0);
    clearSelection();
  };

  const refresh = async () => {
    const requests: Promise<unknown>[] = [workspacesQuery.refetch()];
    if (selectedId) requests.push(creditsQuery.refetch(), historyQuery.refetch());
    await Promise.all(requests);
  };

  const onGranted = async () => {
    if (!selectedId) return;
    setHistoryOffset(0);
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: platformQueryKeys.workspaceCredits(selectedId),
      }),
      queryClient.invalidateQueries({
        queryKey: ['platform', 'workspace', selectedId, 'credits', 'history'],
      }),
    ]);
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="credits-page"
    >
      <DocumentTitle title={t('credits.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-16 -top-20 size-56 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                <Coins className="size-3.5" aria-hidden />
              </span>
              {t('credits.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('credits.title')}
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              {t('credits.subtitle')}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void refresh()}
            disabled={isRefreshing}
            data-testid="credits-refresh"
            className="w-fit bg-background/80"
          >
            <RefreshCw className={cn('size-4', isRefreshing && 'animate-spin')} aria-hidden />
            {t('common.refresh')}
          </Button>
        </div>
      </section>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(320px,0.75fr)_minmax(0,1.35fr)]">
        <Card>
          <CardHeader className="py-4">
            <CardHeading>
              <CardTitle>{t('credits.selectWorkspace')}</CardTitle>
              <CardDescription>{t('credits.workspaceListDescription')}</CardDescription>
            </CardHeading>
            <CardToolbar>
              {workspacesQuery.data ? (
                <Badge variant="secondary" appearance="light" data-testid="credits-workspace-count">
                  {t('credits.workspaceMatchingCount', {
                    count: workspacesQuery.data.total.toLocaleString(i18n.language),
                  })}
                </Badge>
              ) : null}
            </CardToolbar>
          </CardHeader>
          <CardContent className="space-y-5">
            <AdminListFilters
              search={search}
              onSearchChange={(value) => {
                setSearch(value);
                setWorkspaceOffset(0);
                clearSelection();
              }}
              searchPlaceholderKey="workspaces.searchPlaceholder"
              status={status}
              onStatusChange={(value) => {
                setStatus(value);
                setWorkspaceOffset(0);
                clearSelection();
              }}
              statusOptions={[
                { value: 'active', labelKey: 'status.workspace.active' },
                { value: 'suspended', labelKey: 'status.workspace.suspended' },
                { value: 'archived', labelKey: 'status.workspace.archived' },
              ]}
              testIdPrefix="credits-workspaces"
            />

            <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                {hasCustomFilters
                  ? t('credits.customFilterHint')
                  : t('credits.workspaceFilterHint')}
              </p>
              {hasCustomFilters ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={resetFilters}
                  data-testid="credits-reset-filters"
                >
                  {t('common.resetFilters')}
                </Button>
              ) : null}
            </div>

            {workspacesQuery.isLoading ? <WorkspacePickerSkeleton /> : null}

            {workspacesQuery.isError ? (
              <StatePanel
                icon={CircleAlert}
                title={t('credits.workspaceErrorTitle')}
                description={getErrorMessage(workspacesQuery.error, t)}
                action={
                  <Button variant="outline" size="sm" onClick={() => void workspacesQuery.refetch()}>
                    <RefreshCw className="size-3.5" aria-hidden />
                    {t('common.retry')}
                  </Button>
                }
                destructive
                compact
                testId="credits-workspaces-error"
              />
            ) : null}

            {workspacesQuery.isSuccess && workspacesQuery.data.items.length === 0 ? (
              <StatePanel
                icon={SearchX}
                title={t('credits.workspaceEmptyTitle')}
                description={t('credits.noWorkspaces')}
                action={
                  hasCustomFilters ? (
                    <Button variant="outline" size="sm" onClick={resetFilters}>
                      {t('common.resetFilters')}
                    </Button>
                  ) : undefined
                }
                compact
                testId="credits-workspaces-empty"
              />
            ) : null}

            {workspacesQuery.isSuccess && workspacesQuery.data.items.length > 0 ? (
              <>
                <ul
                  className="divide-y divide-border overflow-hidden rounded-xl border border-border"
                  data-testid="credits-workspace-list"
                >
                  {workspacesQuery.data.items.map((workspace) => (
                    <WorkspacePickerRow
                      key={workspace.id}
                      workspace={workspace}
                      selected={selectedId === workspace.id}
                      onSelect={() => {
                        setSelectedWorkspace(workspace);
                        setHistoryOffset(0);
                      }}
                    />
                  ))}
                </ul>
                <AdminPagination
                  total={workspacesQuery.data.total}
                  limit={workspacesQuery.data.limit}
                  offset={workspacesQuery.data.offset}
                  onPageChange={setWorkspaceOffset}
                  testId="credits-workspaces-pagination"
                />
              </>
            ) : null}
          </CardContent>
        </Card>

        {!selectedWorkspace ? (
          <Card className="min-h-[32rem]">
            <CardHeader className="py-4">
              <CardHeading>
                <CardTitle>{t('credits.balanceCard')}</CardTitle>
                <CardDescription>{t('credits.accountDescription')}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="grow">
              <StatePanel
                icon={WalletCards}
                title={t('credits.pickTitle')}
                description={t('credits.pickHint')}
                testId="credits-pick-hint"
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="py-4">
              <CardHeading className="min-w-0">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-primary/15 bg-primary/8 text-primary">
                    <Building2 className="size-5" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <CardTitle className="truncate">{selectedWorkspace.name}</CardTitle>
                    <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                      <bdi dir="ltr" className="font-mono">{selectedWorkspace.slug}</bdi>
                      <WorkspaceStatusBadge status={selectedWorkspace.status} />
                    </CardDescription>
                  </div>
                </div>
              </CardHeading>
              <CardToolbar className="flex-wrap">
                <Button variant="outline" size="sm" asChild>
                  <Link
                    to={`/credits/${selectedWorkspace.id}`}
                    data-testid="credits-open-account"
                  >
                    <WalletCards className="size-3.5" aria-hidden />
                    {t('credits.openAccount')}
                  </Link>
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <Link to={`/workspaces/${selectedWorkspace.id}`}>
                    <ExternalLink className="size-3.5" aria-hidden />
                    {t('credits.openWorkspace')}
                  </Link>
                </Button>
                <Button
                  size="sm"
                  onClick={() => setGrantOpen(true)}
                  disabled={!creditsQuery.isSuccess || creditsQuery.isFetching}
                  data-testid="credits-grant-button"
                >
                  <Coins className="size-3.5" aria-hidden />
                  {t('credits.grant')}
                </Button>
              </CardToolbar>
            </CardHeader>
            <CardContent
              className="space-y-6"
              aria-busy={creditsQuery.isLoading || historyQuery.isLoading}
            >
              {creditsQuery.isError ? (
                <div
                  className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
                  role="alert"
                  data-testid="credits-balance-error"
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
                className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4"
                aria-label={t('credits.accountSummary')}
                data-testid="credits-account-summary"
              >
                <AccountMetric
                  icon={Coins}
                  label={t('credits.balance')}
                  value={formatInteger(creditsQuery.data?.balance, i18n.language)}
                  loading={creditsQuery.isLoading}
                  tone="primary"
                  testId="credits-balance"
                />
                <AccountMetric
                  icon={History}
                  label={t('credits.stats.ledgerEntries')}
                  value={formatInteger(historyQuery.data?.total, i18n.language)}
                  loading={historyQuery.isLoading}
                  tone="info"
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
                    latestEntry && creditLedgerDelta(latestEntry) < 0
                      ? 'warning'
                      : 'success'
                  }
                />
                <AccountMetric
                  icon={Layers3}
                  label={t('credits.stats.currentPlan')}
                  value={selectedWorkspace.current_plan_name ?? t('workspaces.noPlan')}
                  loading={false}
                  tone="neutral"
                />
              </section>

              <section className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="flex items-center gap-2 text-sm font-semibold">
                      <History className="size-4 text-primary" aria-hidden />
                      {t('credits.history')}
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t('credits.historyDescription')}
                    </p>
                  </div>
                  {historyQuery.data ? (
                    <Badge variant="secondary" appearance="light">
                      {t('credits.entryCount', {
                        count: historyQuery.data.total,
                        formattedCount: historyQuery.data.total.toLocaleString(i18n.language),
                      })}
                    </Badge>
                  ) : null}
                </div>

                {historyQuery.isLoading ? <LedgerSkeleton /> : null}

                {historyQuery.isError ? (
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
                    compact
                    testId="credits-history-error"
                  />
                ) : null}

                {historyQuery.isSuccess && historyQuery.data.items.length === 0 ? (
                  <StatePanel
                    icon={History}
                    title={t('credits.historyEmptyTitle')}
                    description={t('credits.historyEmpty')}
                    compact
                    testId="credits-history-empty"
                  />
                ) : null}

                {historyQuery.isSuccess && historyQuery.data.items.length > 0 ? (
                  <>
                    <div
                      className="overflow-hidden rounded-xl border border-border"
                      data-testid="credits-history-list"
                    >
                      <div className="hidden grid-cols-[minmax(100px,0.6fr)_minmax(180px,1.35fr)_minmax(95px,0.7fr)_minmax(80px,0.55fr)_minmax(115px,0.8fr)] gap-4 border-b border-border bg-muted/45 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground rtl:tracking-normal 2xl:grid">
                        <span>{t('credits.columns.type')}</span>
                        <span>{t('credits.columns.reason')}</span>
                        <span>{t('credits.columns.source')}</span>
                        <span>{t('credits.columns.change')}</span>
                        <span>{t('credits.columns.occurred')}</span>
                      </div>
                      <ul className="divide-y divide-border">
                        {historyQuery.data.items.map((entry) => (
                          <CreditLedgerRow key={entry.id} entry={entry} locale={i18n.language} />
                        ))}
                      </ul>
                    </div>
                    <AdminPagination
                      total={historyQuery.data.total}
                      limit={historyQuery.data.limit}
                      offset={historyQuery.data.offset}
                      onPageChange={setHistoryOffset}
                      testId="credits-history-pagination"
                    />
                  </>
                ) : null}
              </section>
            </CardContent>
          </Card>
        )}
      </div>

      {selectedWorkspace && creditsQuery.isSuccess ? (
        <GrantCreditsDialog
          open={grantOpen}
          onOpenChange={setGrantOpen}
          workspaceId={selectedWorkspace.id}
          workspaceName={selectedWorkspace.name}
          currentBalance={creditsQuery.data.balance}
          onGranted={onGranted}
        />
      ) : null}
    </div>
  );
}

function WorkspacePickerRow({
  workspace,
  selected,
  onSelect,
}: {
  workspace: PlatformWorkspaceListItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();

  return (
    <li>
      <button
        type="button"
        className={cn(
          'group flex w-full items-center gap-3 p-3 text-start transition-colors hover:bg-muted/35 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
          selected && 'bg-primary/[0.07]',
        )}
        onClick={onSelect}
        aria-pressed={selected}
        data-testid="credits-workspace-row"
      >
        <span
          className={cn(
            'flex size-10 shrink-0 items-center justify-center rounded-xl border',
            selected
              ? 'border-primary/25 bg-primary text-primary-foreground'
              : 'border-primary/15 bg-primary/8 text-primary',
          )}
          aria-hidden
        >
          {selected ? <Check className="size-5" /> : <Building2 className="size-5" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold group-hover:text-primary">
              {workspace.name}
            </span>
            <WorkspaceStatusBadge status={workspace.status} />
          </span>
          <span className="mt-1 block truncate font-mono text-xs text-muted-foreground">
            <bdi dir="ltr">{workspace.slug}</bdi>
          </span>
          <span className="mt-1 block truncate text-xs text-muted-foreground">
            {workspace.current_plan_name ?? t('workspaces.noPlan')}
          </span>
        </span>
        <ChevronRight
          className={cn(
            'size-4 shrink-0 text-muted-foreground transition-transform rtl:rotate-180',
            selected ? 'text-primary' : 'group-hover:translate-x-0.5 rtl:group-hover:-translate-x-0.5',
          )}
          aria-hidden
        />
      </button>
    </li>
  );
}

type MetricTone = 'primary' | 'success' | 'warning' | 'info' | 'neutral';

function AccountMetric({
  icon: Icon,
  label,
  value,
  loading,
  tone,
  testId,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  loading: boolean;
  tone: MetricTone;
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
    <div className="flex min-h-24 items-center justify-between gap-3 rounded-xl border border-border bg-muted/15 p-4">
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        {loading ? (
          <div className="mt-2 h-6 w-20 animate-pulse rounded bg-muted" />
        ) : (
          <p className="mt-1 truncate text-xl font-semibold tabular-nums" data-testid={testId}>
            {value}
          </p>
        )}
      </div>
      <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-xl', tones[tone])}>
        <Icon className="size-4.5" aria-hidden />
      </span>
    </div>
  );
}

function WorkspacePickerSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border" aria-hidden>
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="flex items-center gap-3 border-b border-border p-3 last:border-0">
          <div className="size-10 animate-pulse rounded-xl bg-muted" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-32 animate-pulse rounded bg-muted" />
            <div className="h-3 w-24 animate-pulse rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

function LedgerSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border" aria-hidden>
      <div className="h-10 animate-pulse border-b border-border bg-muted/50" />
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="flex items-center gap-4 border-b border-border p-4 last:border-0">
          <div className="h-5 w-20 animate-pulse rounded bg-muted" />
          <div className="h-3.5 flex-1 animate-pulse rounded bg-muted" />
          <div className="hidden h-3.5 w-24 animate-pulse rounded bg-muted sm:block" />
        </div>
      ))}
    </div>
  );
}

function StatePanel({
  icon: Icon,
  title,
  description,
  action,
  destructive = false,
  compact = false,
  testId,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  destructive?: boolean;
  compact?: boolean;
  testId: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 text-center',
        compact ? 'min-h-44 py-8' : 'min-h-80 py-12',
      )}
      data-testid={testId}
      role={destructive ? 'alert' : undefined}
    >
      <span
        className={cn(
          'mb-4 flex size-11 items-center justify-center rounded-xl',
          destructive
            ? 'bg-destructive/10 text-destructive'
            : 'bg-primary/10 text-primary',
        )}
      >
        <Icon className="size-5" aria-hidden />
      </span>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
