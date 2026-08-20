import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  BadgeCheck,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  RefreshCw,
  SearchX,
  ShieldCheck,
  UserX,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { PlatformRoleBadge, UserStatusBadge } from '@/components/shared/StatusBadges';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
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
import { fetchPlatformUsers, platformQueryKeys } from '@/services/api/platform';
import type { PlatformUserListItem } from '@/services/api/types';

const PAGE_SIZE = 25;

export function UsersPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [platformRole, setPlatformRole] = useState('');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      platform_role: platformRole || undefined,
    }),
    [offset, search, status, platformRole],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.users(filters),
    queryFn: () => fetchPlatformUsers(filters),
  });

  const summaryQuery = useQuery({
    queryKey: ['platform', 'users', 'inventory-summary'],
    queryFn: async () => {
      const [allUsers, activeUsers, disabledUsers, administrators] = await Promise.all([
        fetchPlatformUsers({ limit: 1, offset: 0 }),
        fetchPlatformUsers({ limit: 1, offset: 0, status: 'active' }),
        fetchPlatformUsers({ limit: 1, offset: 0, status: 'disabled' }),
        fetchPlatformUsers({ limit: 1, offset: 0, platform_role: 'admin' }),
      ]);
      return {
        total: allUsers.total,
        active: activeUsers.total,
        disabled: disabledUsers.total,
        admins: administrators.total,
      };
    },
    staleTime: 30_000,
  });

  const onSearchChange = (value: string) => {
    setSearch(value);
    setOffset(0);
  };

  const hasCustomFilters = Boolean(search || status || platformRole);
  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setPlatformRole('');
    setOffset(0);
  };

  const refresh = async () => {
    await Promise.all([query.refetch(), summaryQuery.refetch()]);
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="users-page"
    >
      <DocumentTitle title={t('users.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-16 -top-20 size-56 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                <UsersRound className="size-3.5" aria-hidden />
              </span>
              {t('users.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('users.title')}
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              {t('users.subtitle')}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void refresh()}
            disabled={query.isFetching || summaryQuery.isFetching}
            data-testid="users-refresh"
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
        aria-label={t('users.inventorySummary')}
        data-testid="user-inventory-summary"
      >
        <InventoryMetric
          icon={UsersRound}
          label={t('users.stats.total')}
          value={summaryQuery.data?.total}
          loading={summaryQuery.isLoading}
          tone="primary"
          locale={i18n.language}
          testId="user-stat-total"
        />
        <InventoryMetric
          icon={CheckCircle2}
          label={t('users.stats.active')}
          value={summaryQuery.data?.active}
          loading={summaryQuery.isLoading}
          tone="success"
          locale={i18n.language}
          testId="user-stat-active"
        />
        <InventoryMetric
          icon={UserX}
          label={t('users.stats.disabled')}
          value={summaryQuery.data?.disabled}
          loading={summaryQuery.isLoading}
          tone="warning"
          locale={i18n.language}
          testId="user-stat-disabled"
        />
        <InventoryMetric
          icon={ShieldCheck}
          label={t('users.stats.admins')}
          value={summaryQuery.data?.admins}
          loading={summaryQuery.isLoading}
          tone="info"
          locale={i18n.language}
          testId="user-stat-admins"
        />
      </section>

      <Card>
        <CardHeader className="py-4">
          <CardHeading>
            <CardTitle>{t('users.listTitle')}</CardTitle>
            <CardDescription>{t('users.listDescription')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            {query.data ? (
              <Badge variant="secondary" appearance="light" data-testid="user-results-count">
                {t('users.matchingCount', {
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
            searchPlaceholderKey="users.searchPlaceholder"
            status={status}
            onStatusChange={(value) => {
              setStatus(value);
              setOffset(0);
            }}
            statusOptions={[
              { value: 'active', labelKey: 'status.user.active' },
              { value: 'disabled', labelKey: 'status.user.disabled' },
            ]}
            secondary={platformRole}
            onSecondaryChange={(value) => {
              setPlatformRole(value);
              setOffset(0);
            }}
            secondaryOptions={[
              { value: 'admin', labelKey: 'status.platformRole.admin' },
              { value: 'none', labelKey: 'status.platformRole.none' },
            ]}
            secondaryLabelKey="users.platformRole"
            testIdPrefix="users"
          />

          <div className="flex min-h-7 flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              {hasCustomFilters ? t('users.customFilterHint') : t('users.filterHint')}
            </p>
            {hasCustomFilters ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={resetFilters}
                data-testid="users-reset-filters"
              >
                {t('common.resetFilters')}
              </Button>
            ) : null}
          </div>

          {query.isLoading ? <UserListSkeleton /> : null}

          {query.isError ? (
            <StatePanel
              icon={CircleAlert}
              title={t('users.errorTitle')}
              description={getErrorMessage(query.error, t)}
              action={
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  <RefreshCw className="size-3.5" aria-hidden />
                  {t('common.retry')}
                </Button>
              }
              destructive
              testId="users-error"
            />
          ) : null}

          {query.isSuccess && query.data.items.length === 0 ? (
            <StatePanel
              icon={SearchX}
              title={t('users.emptyTitle')}
              description={t('users.empty')}
              action={
                hasCustomFilters ? (
                  <Button variant="outline" size="sm" onClick={resetFilters}>
                    {t('common.resetFilters')}
                  </Button>
                ) : undefined
              }
              testId="users-empty"
            />
          ) : null}

          {query.isSuccess && query.data.items.length > 0 ? (
            <>
              <div className="overflow-hidden rounded-xl border border-border" data-testid="users-list">
                <div className="hidden grid-cols-[minmax(260px,1.7fr)_minmax(150px,0.9fr)_minmax(130px,0.65fr)_minmax(130px,0.75fr)_minmax(120px,0.65fr)_24px] gap-4 border-b border-border bg-muted/45 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground rtl:tracking-normal xl:grid">
                  <span>{t('users.columns.user')}</span>
                  <span>{t('users.columns.access')}</span>
                  <span>{t('users.columns.workspaces')}</span>
                  <span>{t('users.columns.lastActivity')}</span>
                  <span>{t('users.columns.joined')}</span>
                  <span className="sr-only">{t('users.columns.open')}</span>
                </div>
                <ul className="divide-y divide-border">
                  {query.data.items.map((user) => (
                    <UserRow key={user.id} user={user} locale={i18n.language} />
                  ))}
                </ul>
              </div>
              <AdminPagination
                total={query.data.total}
                limit={query.data.limit}
                offset={query.data.offset}
                onPageChange={setOffset}
                testId="users-pagination"
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function UserRow({ user, locale }: { user: PlatformUserListItem; locale: string }) {
  const { t } = useTranslation();
  const isVerified = Boolean(user.email_verified_at);

  return (
    <li>
      <Link
        to={`/users/${user.id}`}
        className="group grid gap-4 p-4 transition-colors hover:bg-muted/35 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring xl:grid-cols-[minmax(260px,1.7fr)_minmax(150px,0.9fr)_minmax(130px,0.65fr)_minmax(130px,0.75fr)_minmax(120px,0.65fr)_24px] xl:items-center"
        data-testid="user-row"
      >
        <div className="flex min-w-0 items-center gap-3">
          <Avatar className="size-10">
            <AvatarFallback
              className={cn(
                'font-semibold',
                user.platform_role === 'admin'
                  ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/60 dark:text-violet-300'
                  : 'border-primary/15 bg-primary/10 text-primary',
              )}
            >
              {initials(user.email)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold group-hover:text-primary">
              <bdi dir="ltr">{user.email}</bdi>
            </p>
            <p
              className={cn(
                'mt-0.5 inline-flex items-center gap-1 text-xs',
                isVerified
                  ? 'text-green-700 dark:text-green-300'
                  : 'text-amber-700 dark:text-amber-300',
              )}
            >
              {isVerified ? (
                <BadgeCheck className="size-3.5" aria-hidden />
              ) : (
                <CircleAlert className="size-3.5" aria-hidden />
              )}
              {isVerified ? t('users.verified') : t('users.unverified')}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <UserStatusBadge status={user.status} />
          <PlatformRoleBadge role={user.platform_role} />
        </div>

        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <UsersRound className="size-3.5" aria-hidden />
          {t('users.workspacesCount', { count: user.workspace_memberships_count })}
        </div>

        <div className="text-xs text-muted-foreground">
          <span className="xl:sr-only">{t('users.columns.lastActivity')}: </span>
          <span className="tabular-nums">{formatAdminDate(user.last_login_at, locale)}</span>
        </div>

        <div className="text-xs text-muted-foreground">
          <span className="xl:sr-only">{t('users.columns.joined')}: </span>
          <span className="tabular-nums">{formatAdminDate(user.created_at, locale)}</span>
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

function UserListSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border" data-testid="users-loading">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={index}
          className="flex items-center gap-3 border-b border-border p-4 last:border-b-0"
        >
          <div className="size-10 shrink-0 animate-pulse rounded-full bg-muted" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3.5 w-48 max-w-full animate-pulse rounded bg-muted" />
            <div className="h-3 w-24 animate-pulse rounded bg-muted" />
          </div>
          <div className="hidden h-6 w-28 animate-pulse rounded bg-muted sm:block" />
          <div className="hidden h-4 w-24 animate-pulse rounded bg-muted lg:block" />
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

function initials(value: string): string {
  const localPart = value.trim().split('@')[0] || value.trim();
  const parts = localPart.split(/[._\s-]+/).filter(Boolean);
  return (parts.slice(0, 2).map((part) => part[0]).join('') || '?').toUpperCase();
}
