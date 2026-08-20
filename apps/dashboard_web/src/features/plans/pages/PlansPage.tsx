import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Archive,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Layers3,
  Plus,
  RefreshCw,
  SearchX,
  Sparkles,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { PlanStatusBadge } from '@/components/shared/StatusBadges';
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
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformPlans, platformQueryKeys } from '@/services/api/platform';
import type { PlatformPlanListItem } from '@/services/api/types';

const PAGE_SIZE = 25;
const SUMMARY_PAGE_SIZE = 100;

async function fetchPlanInventory() {
  const firstPage = await fetchPlatformPlans({ limit: SUMMARY_PAGE_SIZE, offset: 0 });
  const remainingOffsets = Array.from(
    { length: Math.max(0, Math.ceil(firstPage.total / SUMMARY_PAGE_SIZE) - 1) },
    (_, index) => (index + 1) * SUMMARY_PAGE_SIZE,
  );
  const remainingPages = await Promise.all(
    remainingOffsets.map((offset) =>
      fetchPlatformPlans({ limit: SUMMARY_PAGE_SIZE, offset }),
    ),
  );
  const items = [firstPage, ...remainingPages].flatMap((page) => page.items);

  return {
    total: firstPage.total,
    active: items.filter((plan) => plan.status === 'active').length,
    archived: items.filter((plan) => plan.status === 'archived').length,
    subscribers: items.reduce((sum, plan) => sum + plan.subscriber_count, 0),
  };
}

export function PlansPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
    }),
    [offset, search, status],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.plans(filters),
    queryFn: () => fetchPlatformPlans(filters),
  });

  const summaryQuery = useQuery({
    queryKey: ['platform', 'plans', 'inventory-summary'],
    queryFn: fetchPlanInventory,
    staleTime: 30_000,
  });

  const hasCustomFilters = Boolean(search || status);
  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setOffset(0);
  };

  const refresh = async () => {
    await Promise.all([query.refetch(), summaryQuery.refetch()]);
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="plans-page"
    >
      <DocumentTitle title={t('plans.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-16 -top-20 size-56 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                <Layers3 className="size-3.5" aria-hidden />
              </span>
              {t('plans.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('plans.title')}
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              {t('plans.subtitle')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void refresh()}
              disabled={query.isFetching || summaryQuery.isFetching}
              data-testid="plans-refresh"
              className="bg-background/80"
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
            <Button asChild data-testid="plans-create-button">
              <Link to="/plans/new">
                <Plus className="size-4" aria-hidden />
                {t('plans.create')}
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('plans.inventorySummary')}
        data-testid="plan-inventory-summary"
      >
        <InventoryMetric
          icon={Layers3}
          label={t('plans.stats.total')}
          value={summaryQuery.data?.total}
          loading={summaryQuery.isLoading}
          tone="primary"
          locale={i18n.language}
          testId="plan-stat-total"
        />
        <InventoryMetric
          icon={CheckCircle2}
          label={t('plans.stats.active')}
          value={summaryQuery.data?.active}
          loading={summaryQuery.isLoading}
          tone="success"
          locale={i18n.language}
          testId="plan-stat-active"
        />
        <InventoryMetric
          icon={Archive}
          label={t('plans.stats.archived')}
          value={summaryQuery.data?.archived}
          loading={summaryQuery.isLoading}
          tone="warning"
          locale={i18n.language}
          testId="plan-stat-archived"
        />
        <InventoryMetric
          icon={UsersRound}
          label={t('plans.stats.subscribers')}
          value={summaryQuery.data?.subscribers}
          loading={summaryQuery.isLoading}
          tone="info"
          locale={i18n.language}
          testId="plan-stat-subscribers"
        />
      </section>

      {summaryQuery.isError ? (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
          data-testid="plan-inventory-error"
        >
          <div className="flex min-w-0 items-start gap-3">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
            <div>
              <p className="text-sm font-semibold text-destructive">
                {t('plans.summaryErrorTitle')}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t('plans.summaryErrorHint')}
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => void summaryQuery.refetch()}>
            <RefreshCw className="size-3.5" aria-hidden />
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      <Card>
        <CardHeader className="py-4">
          <CardHeading>
            <CardTitle>{t('plans.listTitle')}</CardTitle>
            <CardDescription>{t('plans.listDescription')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            {query.data ? (
              <Badge variant="secondary" appearance="light" data-testid="plan-results-count">
                {t('plans.matchingCount', {
                  count: query.data.total,
                  formattedCount: query.data.total.toLocaleString(i18n.language),
                })}
              </Badge>
            ) : null}
          </CardToolbar>
        </CardHeader>
        <CardContent
          className="space-y-5"
          aria-busy={query.isLoading || query.isFetching}
        >
          <AdminListFilters
            search={search}
            onSearchChange={(v) => {
              setSearch(v);
              setOffset(0);
            }}
            searchPlaceholderKey="plans.searchPlaceholder"
            status={status}
            onStatusChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
            statusOptions={[
              { value: 'active', labelKey: 'status.plan.active' },
              { value: 'archived', labelKey: 'status.plan.archived' },
            ]}
            testIdPrefix="plans"
          />

          <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              {hasCustomFilters ? t('plans.customFilterHint') : t('plans.filterHint')}
            </p>
            {hasCustomFilters ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetFilters}
                data-testid="plans-reset-filters"
              >
                {t('common.resetFilters')}
              </Button>
            ) : null}
          </div>

          {query.isLoading ? <PlanListSkeleton /> : null}

          {query.isError ? (
            <StatePanel
              icon={CircleAlert}
              title={t('plans.errorTitle')}
              description={getErrorMessage(query.error, t)}
              action={
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  <RefreshCw className="size-3.5" aria-hidden />
                  {t('common.retry')}
                </Button>
              }
              destructive
              testId="plans-error"
            />
          ) : null}

          {query.isSuccess && query.data.items.length === 0 ? (
            <StatePanel
              icon={SearchX}
              title={t('plans.emptyTitle')}
              description={t('plans.empty')}
              action={
                hasCustomFilters ? (
                  <Button variant="outline" size="sm" onClick={resetFilters}>
                    {t('common.resetFilters')}
                  </Button>
                ) : (
                  <Button asChild size="sm">
                    <Link to="/plans/new">{t('plans.create')}</Link>
                  </Button>
                )
              }
              testId="plans-empty"
            />
          ) : null}

          {query.isSuccess && query.data.items.length > 0 ? (
            <>
              <div
                className="overflow-hidden rounded-xl border border-border"
                data-testid="plans-list"
              >
                <div className="hidden grid-cols-[minmax(260px,1.5fr)_minmax(170px,0.85fr)_minmax(110px,0.55fr)_minmax(130px,0.65fr)_minmax(120px,0.65fr)_minmax(110px,0.55fr)_24px] gap-4 border-b border-border bg-muted/45 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground rtl:tracking-normal 2xl:grid">
                  <span>{t('plans.columns.plan')}</span>
                  <span>{t('plans.columns.status')}</span>
                  <span>{t('plans.columns.price')}</span>
                  <span>{t('plans.columns.subscribers')}</span>
                  <span>{t('plans.columns.entitlements')}</span>
                  <span>{t('plans.columns.updated')}</span>
                  <span className="sr-only">{t('plans.columns.open')}</span>
                </div>
                <ul className="divide-y divide-border">
                  {query.data.items.map((plan) => (
                    <PlanRow key={plan.id} plan={plan} locale={i18n.language} />
                  ))}
                </ul>
              </div>
              <AdminPagination
                total={query.data.total}
                limit={query.data.limit}
                offset={query.data.offset}
                onPageChange={setOffset}
                testId="plans-pagination"
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function PlanRow({ plan, locale }: { plan: PlatformPlanListItem; locale: string }) {
  const { t } = useTranslation();

  return (
    <li>
      <Link
        to={`/plans/${plan.id}`}
        className="group grid gap-4 p-4 transition-colors hover:bg-muted/35 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring md:grid-cols-2 md:items-center 2xl:grid-cols-[minmax(260px,1.5fr)_minmax(170px,0.85fr)_minmax(110px,0.55fr)_minmax(130px,0.65fr)_minmax(120px,0.65fr)_minmax(110px,0.55fr)_24px]"
        data-testid="plan-row"
      >
        <div className="flex min-w-0 items-center gap-3">
          <span
            className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-primary/15 bg-primary/8 text-primary"
            aria-hidden
          >
            <Layers3 className="size-5" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold group-hover:text-primary">{plan.name}</p>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {plan.description || t('plans.noDescription')}
            </p>
            <p className="mt-1 truncate font-mono text-[11px] font-bold text-muted-foreground">
              <bdi dir="ltr">{plan.code}</bdi>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <PlanStatusBadge status={plan.status} />
          {plan.is_bootstrap ? (
            <Badge variant="info" appearance="light" size="sm" data-testid="plan-bootstrap-badge">
              {t('plans.bootstrap')}
            </Badge>
          ) : null}
          {plan.is_commercial ? (
            <Badge variant="secondary" appearance="light" size="sm">
              {t('plans.commercial')}
            </Badge>
          ) : null}
        </div>

        <div className="text-sm font-medium tabular-nums" data-testid="plan-price">
          <span className="text-xs font-normal text-muted-foreground 2xl:sr-only">
            {t('plans.columns.price')}: {' '}
          </span>
          <bdi dir="ltr">{formatMoney(plan.price_amount, plan.currency)}</bdi>
        </div>

        <div
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
          data-testid="plan-subscribers"
        >
          <UsersRound className="size-3.5" aria-hidden />
          {t('plans.subscribers', {
            count: plan.subscriber_count,
            formattedCount: plan.subscriber_count.toLocaleString(locale),
          })}
        </div>

        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="size-3.5" aria-hidden />
          {t('plans.entitlementsCount', {
            count: plan.entitlements.length,
            formattedCount: plan.entitlements.length.toLocaleString(locale),
          })}
        </div>

        <div className="text-xs text-muted-foreground">
          <span className="2xl:sr-only">{t('plans.columns.updated')}: </span>
          <span className="tabular-nums">{formatAdminDate(plan.updated_at, locale)}</span>
        </div>

        <ChevronRight
          className="hidden size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground rtl:rotate-180 rtl:group-hover:-translate-x-0.5 2xl:block"
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
  testId,
}: {
  icon: LucideIcon;
  label: string;
  value: number | undefined;
  loading: boolean;
  tone: MetricTone;
  locale: string;
  testId: string;
}) {
  const tones: Record<MetricTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  };

  return (
    <Card className="min-h-28" data-testid={testId}>
      <CardContent className="flex items-center justify-between gap-4 p-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? (
            <div className="mt-2 h-7 w-16 animate-pulse rounded bg-muted" />
          ) : (
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {value == null ? '—' : value.toLocaleString(locale)}
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

function PlanListSkeleton() {
  const { t } = useTranslation();

  return (
    <div
      className="overflow-hidden rounded-xl border border-border"
      data-testid="plans-loading"
      role="status"
      aria-label={t('common.loading')}
    >
      <div aria-hidden>
        <div className="h-10 animate-pulse border-b border-border bg-muted/50" />
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="flex items-center gap-3 border-b border-border p-4 last:border-0">
            <div className="size-10 animate-pulse rounded-xl bg-muted" />
            <div className="flex-1 space-y-2">
              <div className="h-3.5 w-36 animate-pulse rounded bg-muted" />
              <div className="h-3 w-56 max-w-full animate-pulse rounded bg-muted" />
            </div>
            <div className="hidden h-6 w-20 animate-pulse rounded bg-muted sm:block" />
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
      className="flex min-h-52 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center"
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
