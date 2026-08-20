import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  ArrowDownRight,
  ArrowUpDown,
  ArrowUpRight,
  Boxes,
  CalendarDays,
  CalendarRange,
  CircleAlert,
  Clock3,
  Coins,
  CreditCard,
  Gauge,
  HardDrive,
  History,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  UsersRound,
} from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { AssignPlanDialog } from '@/features/plans/components/AssignPlanDialog';
import { GrantCreditsDialog } from '@/features/credits/components/GrantCreditsDialog';
import {
  creditEntryTypeKey,
  creditLedgerDelta,
  formatSignedCredits,
} from '@/features/credits/lib/ledger';
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
import { formatAdminDateTime, formatBytes } from '@/lib/dates';
import { entitlementValueAsNumber, formatInteger, formatTokens } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchWorkspaceCredits,
  fetchWorkspaceEntitlements,
  fetchWorkspaceSubscription,
  fetchWorkspaceUsage,
  platformQueryKeys,
} from '@/services/api/platform';
import type {
  PlatformCreditLedgerItem,
  PlatformEntitlementItem,
  PlatformUsageMeter,
} from '@/services/api/types';

type WorkspaceBillingSectionProps = {
  workspaceId: string;
  workspaceName: string;
  isSystem: boolean;
};

export function WorkspaceBillingSection({
  workspaceId,
  workspaceName,
  isSystem,
}: WorkspaceBillingSectionProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [assignOpen, setAssignOpen] = useState(false);
  const [grantOpen, setGrantOpen] = useState(false);

  const subscriptionQuery = useQuery({
    queryKey: platformQueryKeys.workspaceSubscription(workspaceId),
    queryFn: () => fetchWorkspaceSubscription(workspaceId),
    enabled: Boolean(workspaceId) && !isSystem,
    retry: false,
  });

  const entitlementsQuery = useQuery({
    queryKey: platformQueryKeys.workspaceEntitlements(workspaceId),
    queryFn: () => fetchWorkspaceEntitlements(workspaceId),
    enabled: Boolean(workspaceId) && !isSystem,
    retry: false,
  });

  const usageQuery = useQuery({
    queryKey: platformQueryKeys.workspaceUsage(workspaceId),
    queryFn: () => fetchWorkspaceUsage(workspaceId),
    enabled: Boolean(workspaceId) && !isSystem,
    retry: false,
  });

  const creditsQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCredits(workspaceId),
    queryFn: () => fetchWorkspaceCredits(workspaceId),
    enabled: Boolean(workspaceId) && !isSystem,
    retry: false,
  });

  const isRefreshing =
    subscriptionQuery.isFetching ||
    entitlementsQuery.isFetching ||
    usageQuery.isFetching ||
    creditsQuery.isFetching;
  const subscriptionVerified = subscriptionQuery.isSuccess && !subscriptionQuery.isFetching;

  useEffect(() => {
    if (!subscriptionVerified && assignOpen) {
      setAssignOpen(false);
    }
  }, [assignOpen, subscriptionVerified]);

  const refreshBilling = async () => {
    await Promise.all([
      subscriptionQuery.refetch(),
      entitlementsQuery.refetch(),
      usageQuery.refetch(),
      creditsQuery.refetch(),
    ]);
  };

  const invalidateBilling = async () => {
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.workspace(workspaceId) });
    await queryClient.invalidateQueries({
      queryKey: platformQueryKeys.workspaceSubscription(workspaceId),
    });
    await queryClient.invalidateQueries({
      queryKey: platformQueryKeys.workspaceEntitlements(workspaceId),
    });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.workspaceUsage(workspaceId) });
    await queryClient.invalidateQueries({
      queryKey: platformQueryKeys.workspaceCredits(workspaceId),
    });
    await queryClient.invalidateQueries({ queryKey: ['platform', 'workspaces'] });
  };

  if (isSystem) {
    return (
      <Card className="overflow-hidden" data-testid="workspace-billing-section">
        <CardContent className="relative flex min-h-40 items-center overflow-hidden">
          <div className="pointer-events-none absolute -end-16 -top-20 size-52 rounded-full bg-primary/10 blur-3xl" />
          <div className="relative flex max-w-2xl items-start gap-4" data-testid="workspace-billing-system">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl border border-primary/15 bg-primary/10 text-primary">
              <CreditCard className="size-5" aria-hidden />
            </span>
            <div className="pt-0.5">
              <h2 className="text-base font-semibold">{t('billing.title')}</h2>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {t('billing.systemNotBillable')}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <section
      className="space-y-4"
      aria-labelledby="workspace-billing-heading"
      data-testid="workspace-billing-section"
    >
      <div className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.07] via-background to-background p-5">
        <div className="pointer-events-none absolute -end-20 -top-24 size-56 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-start gap-3.5">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-primary/15 bg-primary/10 text-primary shadow-xs">
              <CreditCard className="size-4.5" aria-hidden />
            </span>
            <div className="min-w-0 pt-0.5">
              <h2 id="workspace-billing-heading" className="text-base font-semibold">
                {t('billing.title')}
              </h2>
              <p className="mt-1 truncate text-sm text-muted-foreground">{workspaceName}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void refreshBilling()}
              disabled={isRefreshing}
              data-testid="workspace-billing-refresh"
            >
              <RefreshCw className={cn('size-4', isRefreshing && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            <Button variant="outline" asChild data-testid="workspace-open-credit-account">
              <Link to={`/credits/${encodeURIComponent(workspaceId)}`}>
                <Coins className="size-4" aria-hidden />
                {t('credits.openAccount')}
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                if (subscriptionVerified) setAssignOpen(true);
              }}
              disabled={!subscriptionVerified}
              aria-describedby={
                subscriptionVerified ? undefined : 'workspace-change-plan-verification-status'
              }
              data-testid="workspace-change-plan-button"
            >
              {subscriptionQuery.isFetching ? (
                <RefreshCw className="size-4 animate-spin" aria-hidden />
              ) : subscriptionQuery.isError ? (
                <CircleAlert className="size-4" aria-hidden />
              ) : null}
              {t('billing.changePlan')}
            </Button>
            {!subscriptionVerified ? (
              <span
                id="workspace-change-plan-verification-status"
                className="sr-only"
                role={subscriptionQuery.isError ? 'alert' : 'status'}
              >
                {subscriptionQuery.isError
                  ? getErrorMessage(subscriptionQuery.error, t)
                  : t('common.loading')}
              </span>
            ) : null}
            <Button
              onClick={() => setGrantOpen(true)}
              disabled={!creditsQuery.isSuccess || creditsQuery.isFetching}
              data-testid="workspace-grant-credits-button"
            >
              {t('credits.grant')}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <CardHeader className="gap-3 py-4">
            <CardHeading className="min-w-0">
              <div className="flex items-start gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300">
                  <CreditCard className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 pt-0.5">
                  <CardTitle>{t('billing.subscription')}</CardTitle>
                  <CardDescription className="mt-1 leading-relaxed">
                    {t('workspaces.subscriptionDescription')}
                  </CardDescription>
                </div>
              </div>
            </CardHeading>
            {subscriptionQuery.data ? (
              <CardToolbar className="ms-auto">
                <Badge
                  variant={subscriptionStatusTone(subscriptionQuery.data.status)}
                  appearance="light"
                  size="md"
                >
                  {subscriptionStatusLabel(subscriptionQuery.data.status, t)}
                </Badge>
              </CardToolbar>
            ) : null}
          </CardHeader>
          <CardContent className="min-h-64" aria-busy={subscriptionQuery.isLoading}>
            {subscriptionQuery.isLoading ? (
              <BillingCardSkeleton />
            ) : subscriptionQuery.isError ? (
              <QueryErrorState
                message={getErrorMessage(subscriptionQuery.error, t)}
                pending={subscriptionQuery.isFetching}
                onRetry={() => void subscriptionQuery.refetch()}
                retryLabel={t('common.retry')}
              />
            ) : subscriptionQuery.data ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-violet-200/70 bg-violet-50/70 p-4 dark:border-violet-900/80 dark:bg-violet-950/30">
                  <p className="text-xs font-medium text-violet-700/80 dark:text-violet-300/80">
                    {t('billing.plan')}
                  </p>
                  <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2">
                    <p className="min-w-0 truncate text-xl font-semibold tracking-tight">
                      {subscriptionQuery.data.plan_name}
                    </p>
                    <Badge
                      variant="info"
                      appearance="outline"
                      size="sm"
                      className="max-w-full sm:max-w-48"
                    >
                      <bdi
                        dir="ltr"
                        className="min-w-0 truncate font-mono"
                        title={subscriptionQuery.data.plan_code}
                      >
                        {subscriptionQuery.data.plan_code}
                      </bdi>
                    </Badge>
                  </div>
                </div>
                <dl className="grid gap-2.5 sm:grid-cols-2">
                  <DetailTile
                    label={t('workspaces.started')}
                    value={formatAdminDateTime(
                      subscriptionQuery.data.starts_at,
                      i18n.language,
                    )}
                  />
                  <DetailTile
                    label={t('credits.columns.source')}
                    value={subscriptionQuery.data.source || t('common.none')}
                    mono
                    ltr
                  />
                  <DetailTile
                    className="sm:col-span-2"
                    label={t('billing.period')}
                    value={`${formatAdminDateTime(subscriptionQuery.data.current_period_start, i18n.language)} → ${formatAdminDateTime(subscriptionQuery.data.current_period_end, i18n.language)}`}
                    ltr
                  />
                </dl>
              </div>
            ) : (
              <EmptyState icon={CreditCard} message={t('billing.noSubscription')} />
            )}
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="gap-3 py-4">
            <CardHeading className="min-w-0">
              <div className="flex items-start gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300">
                  <Coins className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 pt-0.5">
                  <CardTitle>{t('billing.credits')}</CardTitle>
                  <CardDescription className="mt-1 leading-relaxed">
                    {t('credits.historyDescription')}
                  </CardDescription>
                </div>
              </div>
            </CardHeading>
          </CardHeader>
          <CardContent className="min-h-64" aria-busy={creditsQuery.isLoading}>
            {creditsQuery.isLoading ? (
              <BillingCardSkeleton />
            ) : creditsQuery.isError ? (
              <QueryErrorState
                message={getErrorMessage(creditsQuery.error, t)}
                pending={creditsQuery.isFetching}
                onRetry={() => void creditsQuery.refetch()}
                retryLabel={t('common.retry')}
              />
            ) : (
              <div className="space-y-4">
                <div className="relative overflow-hidden rounded-xl border border-green-200/70 bg-green-50/70 p-4 dark:border-green-900/80 dark:bg-green-950/30">
                  <div className="pointer-events-none absolute -end-8 -top-12 size-32 rounded-full bg-green-400/10 blur-2xl" />
                  <p className="relative text-xs font-medium text-green-700/80 dark:text-green-300/80">
                    {t('credits.balance')}
                  </p>
                  <p
                    className="relative mt-1 text-3xl font-semibold tracking-tight tabular-nums text-green-800 dark:text-green-200"
                    data-testid="workspace-credit-balance"
                  >
                    <bdi dir="ltr">
                      {formatInteger(creditsQuery.data?.balance ?? 0, i18n.language)}
                    </bdi>
                  </p>
                </div>

                {(creditsQuery.data?.recent ?? []).length ? (
                  <div>
                    <div className="mb-2.5 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                      <History className="size-3.5" aria-hidden />
                      <span>{t('credits.history')}</span>
                    </div>
                    <ul className="divide-y divide-border rounded-xl border border-border/80">
                      {(creditsQuery.data?.recent ?? []).slice(0, 4).map((entry) => (
                        <RecentCreditRow key={entry.id} entry={entry} locale={i18n.language} />
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 rounded-xl border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted">
                      <History className="size-3.5" aria-hidden />
                    </span>
                    <span>{t('credits.historyEmpty')}</span>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card data-testid="workspace-entitlements-card">
        <CardHeader className="gap-3 py-4">
          <CardHeading className="min-w-0">
            <div className="flex items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <SlidersHorizontal className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 pt-0.5">
                <CardTitle>{t('billing.entitlements')}</CardTitle>
                <CardDescription className="mt-1 leading-relaxed">
                  {t('billing.entitlementsDescription')}
                </CardDescription>
              </div>
            </div>
          </CardHeading>
          {entitlementsQuery.data?.plan_name ? (
            <CardToolbar className="ms-auto">
              <Badge
                variant="primary"
                appearance="light"
                size="md"
                className="max-w-48"
                data-testid="workspace-entitlements-plan"
                aria-label={t('billing.effectivePlan', {
                  plan: entitlementsQuery.data.plan_name,
                })}
              >
                <Boxes className="size-3.5" aria-hidden />
                <span className="truncate">{entitlementsQuery.data.plan_name}</span>
              </Badge>
            </CardToolbar>
          ) : null}
        </CardHeader>
        <CardContent aria-busy={entitlementsQuery.isLoading}>
          {entitlementsQuery.isLoading ? (
            <EntitlementsSkeleton />
          ) : entitlementsQuery.isError ? (
            <div
              className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-muted/20 px-4 py-8 text-center"
              role="alert"
            >
              <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <CircleAlert className="size-4" aria-hidden />
              </span>
              <p className="max-w-lg text-sm text-destructive">
                {getErrorMessage(entitlementsQuery.error, t)}
              </p>
              <Button
                variant="outline"
                size="sm"
                disabled={entitlementsQuery.isFetching}
                onClick={() => void entitlementsQuery.refetch()}
              >
                {t('common.retry')}
              </Button>
            </div>
          ) : entitlementsQuery.data?.items.length ? (
            <EntitlementsSummary
              items={entitlementsQuery.data.items}
              locale={i18n.language}
              labelFor={(key) => t(`entitlements.${key}`, { defaultValue: key })}
              aiTitle={t('billing.aiTokenLimits')}
              capacityTitle={t('billing.capacityLimits')}
              otherTitle={t('billing.otherEntitlements')}
            />
          ) : (
            <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed bg-muted/20 px-4 py-8 text-center">
              <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <SlidersHorizontal className="size-4" aria-hidden />
              </span>
              <p className="text-sm text-muted-foreground">{t('billing.noEntitlements')}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="overflow-hidden" data-testid="workspace-usage-card">
        <CardHeader className="gap-3 py-4">
          <CardHeading className="min-w-0">
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300">
                <Gauge className="size-4" aria-hidden />
              </span>
              <CardTitle>{t('billing.usage')}</CardTitle>
            </div>
          </CardHeading>
          {usageQuery.data ? (
            <CardToolbar className="ms-auto">
              <Badge
                variant="success"
                appearance="light"
                size="md"
                aria-label={t('credits.currentBalance', {
                  balance: formatInteger(usageQuery.data.credit_balance, i18n.language),
                })}
              >
                <Coins className="size-3.5" aria-hidden />
                <bdi dir="ltr">
                  {formatInteger(usageQuery.data.credit_balance, i18n.language)}
                </bdi>
              </Badge>
            </CardToolbar>
          ) : null}
        </CardHeader>
        <CardContent aria-busy={usageQuery.isLoading}>
          {usageQuery.isLoading ? (
            <UsageSkeleton />
          ) : usageQuery.isError ? (
            <QueryErrorState
              message={getErrorMessage(usageQuery.error, t)}
              pending={usageQuery.isFetching}
              onRetry={() => void usageQuery.refetch()}
              retryLabel={t('common.retry')}
            />
          ) : usageQuery.data ? (
            <ul className="grid gap-3 md:grid-cols-2" data-testid="workspace-usage-meters">
              <MeterRow
                label={t('entitlements.ai_tokens_daily')}
                meter={usageQuery.data.ai_tokens_daily}
                format={(n) => formatTokens(n, i18n.language)}
              />
              <MeterRow
                label={t('entitlements.ai_tokens_weekly')}
                meter={usageQuery.data.ai_tokens_weekly}
                format={(n) => formatTokens(n, i18n.language)}
              />
              <MeterRow
                label={t('entitlements.ai_tokens_monthly')}
                meter={usageQuery.data.ai_tokens_monthly}
                format={(n) => formatTokens(n, i18n.language)}
              />
              <MeterRow
                label={t('entitlements.experts_limit')}
                meter={usageQuery.data.experts}
                format={(n) => formatInteger(n, i18n.language)}
              />
              <MeterRow
                label={t('entitlements.storage_bytes')}
                meter={usageQuery.data.storage_bytes}
                format={(n) => formatBytes(n, i18n.language)}
              />
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <AssignPlanDialog
        open={assignOpen}
        onOpenChange={setAssignOpen}
        workspaceId={workspaceId}
        currentPlanId={subscriptionQuery.data?.plan_id}
        currentEntitlements={entitlementsQuery.data?.items ?? []}
        onAssigned={invalidateBilling}
      />
      {creditsQuery.isSuccess ? (
        <GrantCreditsDialog
          open={grantOpen}
          onOpenChange={setGrantOpen}
          workspaceId={workspaceId}
          workspaceName={workspaceName}
          currentBalance={creditsQuery.data.balance}
          onGranted={invalidateBilling}
        />
      ) : null}
    </section>
  );
}

type BadgeTone = 'success' | 'warning' | 'destructive' | 'secondary';

function subscriptionStatusTone(status: string): BadgeTone {
  if (status === 'active') return 'success';
  if (status === 'past_due') return 'warning';
  if (status === 'expired') return 'destructive';
  return 'secondary';
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

function DetailTile({
  label,
  value,
  className,
  mono = false,
  ltr = false,
}: {
  label: string;
  value: string;
  className?: string;
  mono?: boolean;
  ltr?: boolean;
}) {
  return (
    <div className={cn('min-w-0 rounded-xl border border-border/80 bg-muted/25 p-3', className)}>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          'mt-1.5 min-w-0 break-words text-sm font-medium tabular-nums',
          mono && 'font-mono text-xs',
        )}
        dir={ltr ? 'ltr' : undefined}
      >
        {value}
      </dd>
    </div>
  );
}

function RecentCreditRow({
  entry,
  locale,
}: {
  entry: PlatformCreditLedgerItem;
  locale: string;
}) {
  const { t } = useTranslation();
  const delta = creditLedgerDelta(entry);
  const EntryIcon = entry.entry_type === 'adjust' ? ArrowUpDown : delta < 0 ? ArrowDownRight : ArrowUpRight;

  return (
    <li
      className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-3 py-3"
      data-testid="credit-recent-row"
    >
      <span
        className={cn(
          'flex size-8 shrink-0 items-center justify-center rounded-lg',
          delta < 0
            ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300'
            : 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
        )}
      >
        <EntryIcon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <p className="truncate text-xs font-semibold">
            {t(`credits.entryTypes.${creditEntryTypeKey(entry.entry_type)}`)}
          </p>
          {entry.source_type ? (
            <Badge variant="secondary" appearance="light" size="xs" className="max-w-32">
              <bdi dir="ltr" className="truncate">
                {entry.source_type}
              </bdi>
            </Badge>
          ) : null}
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground" title={entry.reason || undefined}>
          {entry.reason || t('credits.noReason')}
        </p>
        <p className="mt-1 flex flex-wrap gap-x-1 text-[0.6875rem] tabular-nums text-muted-foreground">
          <bdi dir="ltr">{formatAdminDateTime(entry.created_at, locale)}</bdi>
          {entry.remaining_amount != null ? (
            <span>
              <span aria-hidden>· </span>
              {t('credits.remainingInline', {
                count: formatInteger(entry.remaining_amount, locale),
              })}
            </span>
          ) : null}
        </p>
      </div>
      <span
        className={cn(
          'self-start pt-0.5 text-sm font-semibold tabular-nums',
          delta < 0
            ? 'text-amber-700 dark:text-amber-300'
            : 'text-green-700 dark:text-green-300',
        )}
      >
        <bdi dir="ltr">{formatSignedCredits(delta, locale)}</bdi>
      </span>
    </li>
  );
}

function QueryErrorState({
  message,
  pending,
  onRetry,
  retryLabel,
}: {
  message: string;
  pending: boolean;
  onRetry: () => void;
  retryLabel: string;
}) {
  return (
    <div
      className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 px-4 py-7 text-center"
      role="alert"
    >
      <span className="flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <CircleAlert className="size-4" aria-hidden />
      </span>
      <p className="mt-3 max-w-md text-sm leading-6 text-destructive">{message}</p>
      <Button variant="outline" size="sm" className="mt-4" disabled={pending} onClick={onRetry}>
        {retryLabel}
      </Button>
    </div>
  );
}

function EmptyState({ icon: Icon, message }: { icon: LucideIcon; message: string }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed bg-muted/20 px-4 py-7 text-center">
      <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Icon className="size-4" aria-hidden />
      </span>
      <p className="mt-3 text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

function BillingCardSkeleton() {
  const { t } = useTranslation();

  return (
    <div className="space-y-4" role="status" aria-label={t('common.loading')}>
      <div className="h-20 animate-pulse rounded-xl bg-muted" />
      <div className="grid gap-2.5 sm:grid-cols-2">
        <div className="h-16 animate-pulse rounded-xl bg-muted" />
        <div className="h-16 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}

function UsageSkeleton() {
  const { t } = useTranslation();

  return (
    <div
      className="grid gap-3 md:grid-cols-2"
      role="status"
      aria-label={t('common.loading')}
    >
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="h-24 animate-pulse rounded-xl bg-muted" />
      ))}
    </div>
  );
}

type EntitlementGroupKey = 'ai' | 'capacity' | 'other';
type EntitlementTone = 'primary' | 'success' | 'warning' | 'info';

type EntitlementDisplay = {
  group: EntitlementGroupKey;
  order: number;
  icon: LucideIcon;
  tone: EntitlementTone;
};

const ENTITLEMENT_DISPLAY: Record<string, EntitlementDisplay> = {
  ai_tokens_daily: { group: 'ai', order: 0, icon: Clock3, tone: 'primary' },
  ai_tokens_weekly: { group: 'ai', order: 1, icon: CalendarDays, tone: 'primary' },
  ai_tokens_monthly: { group: 'ai', order: 2, icon: CalendarRange, tone: 'primary' },
  experts_limit: { group: 'capacity', order: 0, icon: UsersRound, tone: 'info' },
  storage_bytes: { group: 'capacity', order: 1, icon: HardDrive, tone: 'warning' },
  api_requests_per_minute: { group: 'capacity', order: 2, icon: Gauge, tone: 'success' },
};

function EntitlementsSummary({
  items,
  locale,
  labelFor,
  aiTitle,
  capacityTitle,
  otherTitle,
}: {
  items: PlatformEntitlementItem[];
  locale: string;
  labelFor: (key: string) => string;
  aiTitle: string;
  capacityTitle: string;
  otherTitle: string;
}) {
  const groups = items.reduce<Record<EntitlementGroupKey, PlatformEntitlementItem[]>>(
    (result, item) => {
      result[ENTITLEMENT_DISPLAY[item.key]?.group ?? 'other'].push(item);
      return result;
    },
    { ai: [], capacity: [], other: [] },
  );

  for (const group of Object.values(groups)) {
    group.sort(
      (a, b) =>
        (ENTITLEMENT_DISPLAY[a.key]?.order ?? Number.MAX_SAFE_INTEGER) -
        (ENTITLEMENT_DISPLAY[b.key]?.order ?? Number.MAX_SAFE_INTEGER),
    );
  }

  return (
    <div className="space-y-5" data-testid="workspace-entitlements-list">
      <EntitlementGroup
        id="workspace-ai-token-limits"
        title={aiTitle}
        icon={Sparkles}
        items={groups.ai}
        locale={locale}
        labelFor={labelFor}
        featured
      />
      <EntitlementGroup
        id="workspace-capacity-limits"
        title={capacityTitle}
        icon={Gauge}
        items={groups.capacity}
        locale={locale}
        labelFor={labelFor}
      />
      <EntitlementGroup
        id="workspace-other-entitlements"
        title={otherTitle}
        icon={SlidersHorizontal}
        items={groups.other}
        locale={locale}
        labelFor={labelFor}
      />
    </div>
  );
}

function EntitlementGroup({
  id,
  title,
  icon: GroupIcon,
  items,
  locale,
  labelFor,
  featured = false,
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  items: PlatformEntitlementItem[];
  locale: string;
  labelFor: (key: string) => string;
  featured?: boolean;
}) {
  if (!items.length) return null;

  return (
    <section aria-labelledby={id}>
      <div className="mb-2.5 flex items-center gap-2 text-muted-foreground">
        <GroupIcon className="size-3.5" aria-hidden />
        <h4 id={id} className="text-xs font-semibold tracking-wide rtl:tracking-normal">
          {title}
        </h4>
      </div>
      <dl className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <EntitlementTile
            key={item.key}
            item={item}
            label={labelFor(item.key)}
            locale={locale}
            featured={featured}
          />
        ))}
      </dl>
    </section>
  );
}

function EntitlementTile({
  item,
  label,
  locale,
  featured,
}: {
  item: PlatformEntitlementItem;
  label: string;
  locale: string;
  featured: boolean;
}) {
  const display = ENTITLEMENT_DISPLAY[item.key];
  const Icon = display?.icon ?? SlidersHorizontal;
  const tone = display?.tone ?? 'primary';
  const tones: Record<EntitlementTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  };
  const value =
    item.key === 'storage_bytes'
      ? formatBytes(entitlementValueAsNumber(item.value), locale)
      : formatInteger(entitlementValueAsNumber(item.value), locale);

  return (
    <div
      className={cn(
        'min-w-0 rounded-xl border border-border/80 bg-muted/30 p-3.5',
        featured && 'border-primary/15 bg-primary/[0.035]',
      )}
      data-entitlement-key={item.key}
    >
      <dt className="flex min-w-0 items-center gap-2.5 text-xs font-medium text-muted-foreground">
        <span
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-lg',
            tones[tone],
          )}
        >
          <Icon className="size-3.5" aria-hidden />
        </span>
        <span className="min-w-0 leading-4">{label}</span>
      </dt>
      <dd className="mt-3 text-start text-2xl font-semibold tracking-tight tabular-nums">
        <span dir="ltr" className="inline-block">
          {value}
        </span>
      </dd>
    </div>
  );
}

function EntitlementsSkeleton() {
  const { t } = useTranslation();

  return (
    <div className="space-y-5" role="status" aria-label={t('common.loading')}>
      {[0, 1].map((group) => (
        <div key={group} className="space-y-2.5">
          <div className="h-3.5 w-32 animate-pulse rounded bg-muted" />
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((item) => (
              <div key={item} className="h-24 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function MeterRow({
  label,
  meter,
  format,
}: {
  label: string;
  meter: PlatformUsageMeter;
  format: (n: number) => string;
}) {
  const used = Math.max(0, meter.used);
  const reserved = Math.max(0, meter.reserved ?? 0);
  const committed = used + reserved;
  const pct =
    meter.limit > 0
      ? Math.max(0, Math.min(100, Math.round((committed / meter.limit) * 100)))
      : 0;
  const progressTone =
    pct >= 90 ? 'bg-destructive' : pct >= 75 ? 'bg-amber-500' : 'bg-primary';

  return (
    <li className="min-w-0 rounded-xl border border-border/80 bg-muted/25 p-3.5">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <span className="min-w-0 text-xs font-medium leading-5 text-muted-foreground">{label}</span>
        <Badge
          variant={pct >= 90 ? 'destructive' : pct >= 75 ? 'warning' : 'primary'}
          appearance="light"
          size="xs"
          className="shrink-0 tabular-nums"
        >
          <bdi dir="ltr">{pct}%</bdi>
        </Badge>
      </div>
      <p
        className="mt-2.5 truncate text-sm font-semibold tabular-nums"
        title={`${format(committed)} / ${format(meter.limit)}`}
      >
        <bdi dir="ltr">
          {format(committed)} / {format(meter.limit)}
        </bdi>
      </p>
      <div
        className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={`${format(committed)} / ${format(meter.limit)}`}
      >
        <div
          className={cn('h-full rounded-full transition-[width]', progressTone)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </li>
  );
}
