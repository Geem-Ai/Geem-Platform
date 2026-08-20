import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import {
  Building2,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Database,
  RefreshCw,
  SearchX,
  ShieldCheck,
  Sparkles,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { WorkspaceKindBadge, WorkspaceStatusBadge } from '@/components/shared/StatusBadges';
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
import { formatAdminDate } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformWorkspaces, platformQueryKeys } from '@/services/api/platform';
import type { PlatformWorkspaceListItem } from '@/services/api/types';

const PAGE_SIZE = 25;

export function WorkspacesPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('tenant');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      kind: kind || 'tenant',
    }),
    [offset, search, status, kind],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.workspaces(filters),
    queryFn: () => fetchPlatformWorkspaces(filters),
  });

  const summaryQuery = useQuery({
    queryKey: ['platform', 'workspaces', 'inventory-summary'],
    queryFn: async () => {
      const [tenants, activeTenants, suspendedTenants, systemWorkspaces] = await Promise.all([
        fetchPlatformWorkspaces({ limit: 1, offset: 0, kind: 'tenant' }),
        fetchPlatformWorkspaces({ limit: 1, offset: 0, kind: 'tenant', status: 'active' }),
        fetchPlatformWorkspaces({ limit: 1, offset: 0, kind: 'tenant', status: 'suspended' }),
        fetchPlatformWorkspaces({ limit: 1, offset: 0, kind: 'system' }),
      ]);
      return {
        tenants: tenants.total,
        activeTenants: activeTenants.total,
        suspendedTenants: suspendedTenants.total,
        systemWorkspaces: systemWorkspaces.total,
      };
    },
    staleTime: 30_000,
  });

  const onSearchChange = (value: string) => {
    setSearch(value);
    setOffset(0);
  };

  const hasCustomFilters = Boolean(search || status || kind !== 'tenant');
  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setKind('tenant');
    setOffset(0);
  };

  const refresh = async () => {
    await Promise.all([query.refetch(), summaryQuery.refetch()]);
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="workspaces-page"
    >
      <DocumentTitle title={t('workspaces.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-16 -top-20 size-56 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                <Database className="size-3.5" aria-hidden />
              </span>
              {t('workspaces.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('workspaces.title')}
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              {t('workspaces.subtitle')}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void refresh()}
            disabled={query.isFetching || summaryQuery.isFetching}
            data-testid="workspaces-refresh"
            className="w-fit bg-background/80"
          >
            <RefreshCw
              className={cn(
                'size-4',
                (query.isFetching || summaryQuery.isFetching) && 'animate-spin',
              )}
              aria-hidden
            />
            {t('common.refresh')}
          </Button>
        </div>
      </section>

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('workspaces.inventorySummary')}
        data-testid="workspace-inventory-summary"
      >
        <InventoryMetric
          icon={Building2}
          label={t('workspaces.stats.tenantTotal')}
          value={summaryQuery.data?.tenants}
          loading={summaryQuery.isLoading}
          tone="primary"
          locale={i18n.language}
        />
        <InventoryMetric
          icon={CheckCircle2}
          label={t('workspaces.stats.activeTenants')}
          value={summaryQuery.data?.activeTenants}
          loading={summaryQuery.isLoading}
          tone="success"
          locale={i18n.language}
        />
        <InventoryMetric
          icon={CircleAlert}
          label={t('workspaces.stats.suspendedTenants')}
          value={summaryQuery.data?.suspendedTenants}
          loading={summaryQuery.isLoading}
          tone="warning"
          locale={i18n.language}
        />
        <InventoryMetric
          icon={ShieldCheck}
          label={t('workspaces.stats.systemSpaces')}
          value={summaryQuery.data?.systemWorkspaces}
          loading={summaryQuery.isLoading}
          tone="info"
          locale={i18n.language}
        />
      </section>

      <Card>
        <CardHeader className="py-4">
          <CardHeading>
            <CardTitle>{t('workspaces.listTitle')}</CardTitle>
            <CardDescription>{t('workspaces.listDescription')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            {query.data ? (
              <Badge variant="secondary" appearance="light" data-testid="workspace-results-count">
                {t('workspaces.matchingCount', {
                  count: query.data.total.toLocaleString(i18n.language),
                })}
              </Badge>
            ) : null}
          </CardToolbar>
        </CardHeader>
        <CardContent className="space-y-5">
          <AdminListFilters
            search={search}
            onSearchChange={onSearchChange}
            searchPlaceholderKey="workspaces.searchPlaceholder"
            status={status}
            onStatusChange={(value) => {
              setStatus(value);
              setOffset(0);
            }}
            statusOptions={[
              { value: 'active', labelKey: 'status.workspace.active' },
              { value: 'suspended', labelKey: 'status.workspace.suspended' },
              { value: 'archived', labelKey: 'status.workspace.archived' },
            ]}
            secondary={kind}
            onSecondaryChange={(value) => {
              setKind(value);
              setOffset(0);
            }}
            secondaryOptions={[
              { value: 'all', labelKey: 'common.all' },
              { value: 'tenant', labelKey: 'status.kind.tenant' },
              { value: 'system', labelKey: 'status.kind.system' },
            ]}
            secondaryLabelKey="workspaces.kind"
            secondaryIncludeBlank={false}
            testIdPrefix="workspaces"
          />

          <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              {kind === 'tenant'
                ? t('workspaces.tenantFilterHint')
                : t('workspaces.customFilterHint')}
            </p>
            {hasCustomFilters ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetFilters}
                data-testid="workspaces-reset-filters"
              >
                {t('common.resetFilters')}
              </Button>
            ) : null}
          </div>

          {query.isLoading ? <WorkspaceListSkeleton /> : null}

          {query.isError ? (
            <StatePanel
              icon={CircleAlert}
              title={t('workspaces.errorTitle')}
              description={getErrorMessage(query.error, t)}
              action={
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  <RefreshCw className="size-3.5" aria-hidden />
                  {t('common.retry')}
                </Button>
              }
              destructive
              testId="workspaces-error"
            />
          ) : null}

          {query.isSuccess && query.data.items.length === 0 ? (
            <StatePanel
              icon={SearchX}
              title={t('workspaces.emptyTitle')}
              description={t('workspaces.empty')}
              action={
                hasCustomFilters ? (
                  <Button variant="outline" size="sm" onClick={resetFilters}>
                    {t('common.resetFilters')}
                  </Button>
                ) : undefined
              }
              testId="workspaces-empty"
            />
          ) : null}

          {query.isSuccess && query.data.items.length > 0 ? (
            <>
              <div
                className="overflow-hidden rounded-xl border border-border"
                data-testid="workspaces-list"
              >
                <div className="hidden grid-cols-[minmax(240px,1.6fr)_minmax(120px,0.7fr)_minmax(150px,0.8fr)_minmax(150px,0.8fr)_minmax(110px,0.55fr)_24px] gap-4 border-b border-border bg-muted/45 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground xl:grid">
                  <span>{t('workspaces.columns.workspace')}</span>
                  <span>{t('workspaces.columns.status')}</span>
                  <span>{t('workspaces.columns.footprint')}</span>
                  <span>{t('workspaces.columns.plan')}</span>
                  <span>{t('workspaces.columns.created')}</span>
                  <span className="sr-only">{t('workspaces.columns.open')}</span>
                </div>
                <ul className="divide-y divide-border">
                  {query.data.items.map((workspace) => (
                    <WorkspaceRow
                      key={workspace.id}
                      workspace={workspace}
                      locale={i18n.language}
                    />
                  ))}
                </ul>
              </div>
              <AdminPagination
                total={query.data.total}
                limit={query.data.limit}
                offset={query.data.offset}
                onPageChange={setOffset}
                testId="workspaces-pagination"
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function WorkspaceRow({
  workspace,
  locale,
}: {
  workspace: PlatformWorkspaceListItem;
  locale: string;
}) {
  const { t } = useTranslation();
  const isSystem = workspace.kind === 'system';

  return (
    <li>
      <Link
        to={`/workspaces/${workspace.id}`}
        className="group grid gap-4 p-4 transition-colors hover:bg-muted/35 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring xl:grid-cols-[minmax(240px,1.6fr)_minmax(120px,0.7fr)_minmax(150px,0.8fr)_minmax(150px,0.8fr)_minmax(110px,0.55fr)_24px] xl:items-center"
        data-testid="workspace-row"
        aria-label={t('workspaces.viewWorkspace', { name: workspace.name })}
      >
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-xl border',
              isSystem
                ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/60 dark:text-violet-300'
                : 'border-primary/15 bg-primary/8 text-primary',
            )}
            aria-hidden
          >
            {isSystem ? <ShieldCheck className="size-5" /> : <Building2 className="size-5" />}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold group-hover:text-primary">
              {workspace.name}
            </p>
            <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
              {workspace.slug}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <WorkspaceStatusBadge status={workspace.status} />
          <WorkspaceKindBadge kind={workspace.kind} />
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5" data-testid="workspace-members-count">
            <UsersRound className="size-3.5" aria-hidden />
            {t('workspaces.membersCount', { count: workspace.members_count })}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="size-3.5" aria-hidden />
            {t('workspaces.expertsCount', { count: workspace.experts_count })}
          </span>
        </div>

        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            {workspace.current_plan_name ?? t('workspaces.noPlan')}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {workspace.subscription_status
              ? subscriptionStatusLabel(workspace.subscription_status, t)
              : t('workspaces.noSubscription')}
          </p>
        </div>

        <div className="text-xs text-muted-foreground">
          <span className="xl:hidden">{t('workspaces.columns.created')}: </span>
          <span className="tabular-nums">{formatAdminDate(workspace.created_at, locale)}</span>
        </div>

        <ChevronRight
          className="hidden size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground rtl:rotate-180 rtl:group-hover:-translate-x-0.5 xl:block"
          aria-hidden
        />
      </Link>
    </li>
  );
}

type MetricTone = 'primary' | 'success' | 'warning' | 'info';

function InventoryMetric({
  icon: Icon,
  label,
  value,
  loading,
  tone,
  locale,
}: {
  icon: LucideIcon;
  label: string;
  value: number | undefined;
  loading: boolean;
  tone: MetricTone;
  locale: string;
}) {
  const tones: Record<MetricTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  };

  return (
    <Card className="min-h-28">
      <CardContent className="flex items-center gap-4 p-4">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tones[tone])}>
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          {loading ? (
            <div className="mb-2 h-7 w-14 animate-pulse rounded bg-muted" />
          ) : (
            <p className="text-2xl font-semibold tabular-nums">
              {value == null ? '—' : value.toLocaleString(locale)}
            </p>
          )}
          <p className="truncate text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function WorkspaceListSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border" data-testid="workspaces-loading">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 border-b border-border p-4 last:border-b-0"
        >
          <div className="size-10 shrink-0 animate-pulse rounded-xl bg-muted" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3.5 w-40 animate-pulse rounded bg-muted" />
            <div className="h-3 w-28 animate-pulse rounded bg-muted" />
          </div>
          <div className="hidden h-6 w-24 animate-pulse rounded bg-muted sm:block" />
          <div className="hidden h-4 w-32 animate-pulse rounded bg-muted lg:block" />
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
    >
      <span
        className={cn(
          'mb-4 flex size-11 items-center justify-center rounded-full',
          destructive ? 'bg-destructive/10 text-destructive' : 'bg-primary/10 text-primary',
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

function subscriptionStatusLabel(status: string, t: TFunction): string {
  const labels: Record<string, string> = {
    active: t('status.subscription.active'),
    canceled: t('status.subscription.canceled'),
    cancelled: t('status.subscription.canceled'),
    expired: t('status.subscription.expired'),
    past_due: t('status.subscription.pastDue'),
  };
  return labels[status] ?? t('status.subscription.unknown');
}
