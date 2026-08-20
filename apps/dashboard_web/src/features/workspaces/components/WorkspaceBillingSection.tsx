import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { LucideIcon } from 'lucide-react';
import {
  Boxes,
  CalendarDays,
  CalendarRange,
  CircleAlert,
  Clock3,
  Gauge,
  HardDrive,
  SlidersHorizontal,
  Sparkles,
  UsersRound,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { AssignPlanDialog } from '@/features/plans/components/AssignPlanDialog';
import { GrantCreditsDialog } from '@/features/credits/components/GrantCreditsDialog';
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
import type { PlatformEntitlementItem, PlatformUsageMeter } from '@/services/api/types';

type WorkspaceBillingSectionProps = {
  workspaceId: string;
  isSystem: boolean;
};

export function WorkspaceBillingSection({ workspaceId, isSystem }: WorkspaceBillingSectionProps) {
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
      <Card data-testid="workspace-billing-section">
        <CardHeader>
          <CardTitle className="text-base">{t('billing.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground" data-testid="workspace-billing-system">
            {t('billing.systemNotBillable')}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4" data-testid="workspace-billing-section">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-base font-semibold">{t('billing.title')}</h2>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => setAssignOpen(true)}
            data-testid="workspace-change-plan-button"
          >
            {t('billing.changePlan')}
          </Button>
          <Button onClick={() => setGrantOpen(true)} data-testid="workspace-grant-credits-button">
            {t('credits.grant')}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('billing.subscription')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {subscriptionQuery.isLoading ? (
              <div className="h-16 animate-pulse rounded bg-muted" />
            ) : subscriptionQuery.isError ? (
              <p className="text-destructive">{getErrorMessage(subscriptionQuery.error, t)}</p>
            ) : subscriptionQuery.data ? (
              <>
                <Row label={t('billing.plan')} value={subscriptionQuery.data.plan_name} />
                <Row
                  label={t('billing.planCode')}
                  value={subscriptionQuery.data.plan_code}
                />
                <Row label={t('billing.status')} value={subscriptionQuery.data.status} />
                <Row
                  label={t('billing.period')}
                  value={`${formatAdminDateTime(subscriptionQuery.data.current_period_start, i18n.language)} → ${formatAdminDateTime(subscriptionQuery.data.current_period_end, i18n.language)}`}
                />
              </>
            ) : (
              <p className="text-muted-foreground">{t('billing.noSubscription')}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('billing.credits')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {creditsQuery.isLoading ? (
              <div className="h-16 animate-pulse rounded bg-muted" />
            ) : creditsQuery.isError ? (
              <p className="text-destructive">{getErrorMessage(creditsQuery.error, t)}</p>
            ) : (
              <>
                <Row
                  label={t('credits.balance')}
                  value={formatInteger(creditsQuery.data?.balance ?? 0, i18n.language)}
                />
                {(creditsQuery.data?.recent ?? []).slice(0, 3).map((entry) => (
                  <div
                    key={entry.id}
                    className="flex justify-between gap-2 text-xs text-muted-foreground border-t pt-2"
                    data-testid="credit-recent-row"
                  >
                    <span>
                      {entry.entry_type}
                      {entry.reason ? ` · ${entry.reason}` : ''}
                    </span>
                    <span className="tabular-nums">
                      {entry.amount > 0 ? '+' : ''}
                      {formatInteger(entry.amount, i18n.language)}
                    </span>
                  </div>
                ))}
              </>
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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('billing.usage')}</CardTitle>
        </CardHeader>
        <CardContent>
          {usageQuery.isLoading ? (
            <div className="h-16 animate-pulse rounded bg-muted" />
          ) : usageQuery.isError ? (
            <p className="text-sm text-destructive">{getErrorMessage(usageQuery.error, t)}</p>
          ) : usageQuery.data ? (
            <ul className="space-y-3" data-testid="workspace-usage-meters">
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
              <li className="flex justify-between gap-2 text-sm">
                <span className="text-muted-foreground">{t('credits.balance')}</span>
                <span className="tabular-nums">
                  {formatInteger(usageQuery.data.credit_balance, i18n.language)}
                </span>
              </li>
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
      <GrantCreditsDialog
        open={grantOpen}
        onOpenChange={setGrantOpen}
        workspaceId={workspaceId}
        onGranted={invalidateBilling}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="sm:text-end break-all">{value}</span>
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
        <h4 id={id} className="text-xs font-semibold tracking-wide">
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
  return (
    <div className="space-y-5" aria-hidden>
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
  const pct = meter.limit > 0 ? Math.min(100, Math.round((meter.used / meter.limit) * 100)) : 0;
  return (
    <li className="space-y-1">
      <div className="flex justify-between gap-2 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">
          {format(meter.used)} / {format(meter.limit)}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </li>
  );
}
