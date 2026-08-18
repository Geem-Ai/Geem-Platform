import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CalendarDays, CreditCard } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { formatPeriodDate, formatRelativeTime } from '@/features/usage/lib/quota';
import type { PurchasablePlan } from '@/services/api/billing';
import type { Entitlements, Subscription } from '@/services/api/usage';
import { MoneyAmount } from './MoneyAmount';
import { EntitlementTiles } from './EntitlementTiles';

function planStatusVariant(status: string): 'success' | 'warning' | 'secondary' {
  if (status === 'active' || status === 'trialing') return 'success';
  if (status === 'past_due') return 'warning';
  return 'secondary';
}

export function CurrentSubscriptionCard({
  subscription,
  entitlements,
  catalogPlan,
}: {
  subscription: Subscription;
  entitlements: Entitlements | undefined;
  catalogPlan: PurchasablePlan | undefined;
}) {
  const { t, i18n } = useTranslation();
  const planStatusKey = `usage.subscriptionStatus.${subscription.status}`;
  const planStatusLabel = i18n.exists(planStatusKey)
    ? t(planStatusKey)
    : subscription.status;
  const periodStart = formatPeriodDate(subscription.current_period_start, i18n.language);
  const periodEnd = formatPeriodDate(subscription.current_period_end, i18n.language);
  const periodEndsRelative = subscription.current_period_end
    ? formatRelativeTime(subscription.current_period_end, i18n.language)
    : null;

  return (
    <Card data-testid="billing-current-subscription" className="shadow-xs overflow-hidden">
      <div className="h-0.5 bg-primary" aria-hidden />
      <CardContent className="p-5 sm:p-6 space-y-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3.5 min-w-0">
            <div className="size-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <CreditCard className="size-5" aria-hidden />
            </div>
            <div className="min-w-0 space-y-2">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {t('billing.currentSubscription')}
              </p>
              <div className="flex flex-wrap items-center gap-2.5">
                <h2
                  className="text-xl font-semibold tracking-tight"
                  data-testid="billing-current-plan-name"
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
                {t('billing.currentSubscriptionHint')}
              </p>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:flex sm:flex-wrap sm:gap-8 lg:justify-end shrink-0">
            {catalogPlan ? (
              <div>
                <dt className="text-xs text-muted-foreground mb-1">
                  {t('billing.catalogPrice')}
                </dt>
                <dd
                  className="text-sm font-semibold tracking-tight"
                  data-testid="billing-current-plan-price"
                >
                  <MoneyAmount
                    amount={catalogPlan.price_amount}
                    currency={catalogPlan.currency}
                  />
                </dd>
              </div>
            ) : null}
            {periodStart && periodEnd ? (
              <div className="lg:text-end">
                <dt className="text-xs text-muted-foreground mb-1">
                  {t('usage.currentPeriod')}
                </dt>
                <dd className="text-sm font-medium tabular-nums">
                  {t('usage.planPeriod', { start: periodStart, end: periodEnd })}
                </dd>
              </div>
            ) : null}
            {periodEndsRelative ? (
              <div className="lg:text-end col-span-2 sm:col-span-1">
                <dt className="text-xs text-muted-foreground mb-1 flex items-center gap-1.5 lg:justify-end">
                  <CalendarDays className="size-3.5" aria-hidden />
                  {t('billing.periodEnds')}
                </dt>
                <dd className="text-sm font-medium">{periodEndsRelative}</dd>
              </div>
            ) : null}
          </dl>
        </div>

        {entitlements?.items.length ? (
          <div className="space-y-2.5">
            <h3 className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
              {t('billing.includedAllowances')}
            </h3>
            <EntitlementTiles
              items={entitlements.items}
              testId="billing-entitlement-summary"
            />
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="outline" size="sm" asChild>
            <Link to="/billing/usage">{t('billing.viewUsage')}</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/billing/credits">{t('billing.buyCredits')}</Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/billing/history">{t('billing.viewHistory')}</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
