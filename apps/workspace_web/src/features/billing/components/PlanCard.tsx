import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { PurchasablePlan } from '@/services/api/billing';
import type { ByteUnitKey } from '@/features/usage/lib/quota';
import {
  entitlementLabelKey,
  formatEntitlementValue,
  isEntitlementI18nValue,
  sortEntitlements,
} from '../lib/entitlements';
import { formatMoney } from '../lib/money';

export function PlanCard({
  plan,
  current,
  checkoutDisabled,
  checkoutPending,
  onChoose,
}: {
  plan: PurchasablePlan;
  current: boolean;
  checkoutDisabled?: boolean;
  checkoutPending?: boolean;
  onChoose: (plan: PurchasablePlan) => void;
}) {
  const { t, i18n } = useTranslation();
  const byteUnit = (unit: ByteUnitKey) => t(`usage.units.${unit}`);
  const entitlements = sortEntitlements(plan.entitlements);

  return (
    <Card
      data-testid={`billing-plan-${plan.id}`}
      data-current={current ? 'true' : 'false'}
      className={cn(
        'shadow-xs overflow-hidden h-full transition-[border-color,box-shadow,background-color] duration-200',
        current
          ? 'border-primary/40 bg-accent/15'
          : 'hover:border-primary/25 hover:shadow-sm hover:bg-accent/10',
      )}
    >
      {current ? <div className="h-0.5 bg-primary" aria-hidden /> : null}
      <CardContent className="p-5 sm:p-6 flex flex-col gap-5 h-full">
        <div className="space-y-3 min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 className="text-base font-semibold tracking-tight">{plan.name}</h3>
            {current ? (
              <Badge
                variant="success"
                appearance="light"
                size="sm"
                data-testid="billing-plan-current"
              >
                {t('billing.currentPlan')}
              </Badge>
            ) : null}
          </div>
          {plan.description ? (
            <p className="text-sm text-muted-foreground leading-relaxed line-clamp-3">
              {plan.description}
            </p>
          ) : null}
          <div>
            <p className="text-2xl font-semibold tabular-nums tracking-tight">
              {formatMoney(plan.price_amount, plan.currency)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {t('billing.billedIn', { currency: plan.currency })}
            </p>
          </div>
        </div>
        {entitlements.length > 0 ? (
          <div className="space-y-2 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
              {t('billing.includedAllowances')}
            </p>
            <ul
              className="space-y-2 text-sm"
              data-testid={`billing-plan-entitlements-${plan.id}`}
            >
              {entitlements.map((item) => {
                const formatted = formatEntitlementValue(item, i18n.language, byteUnit);
                const value = isEntitlementI18nValue(formatted)
                  ? t(formatted)
                  : formatted;
                return (
                  <li
                    key={item.key}
                    data-entitlement-key={item.key}
                    className="flex items-start gap-2"
                  >
                    <Check
                      className="size-4 text-primary mt-0.5 shrink-0"
                      aria-hidden
                    />
                    <span className="min-w-0 leading-5">
                      <span className="text-muted-foreground">
                        {t(entitlementLabelKey(item.key), { key: item.key })}
                      </span>
                      <span className="font-medium text-foreground tabular-nums">
                        {' '}
                        {value}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <div className="flex-1" />
        )}
        {current ? (
          <div className="space-y-1.5">
            <Button
              type="button"
              variant="outline"
              disabled
              className="w-full"
              data-testid="billing-plan-cta"
            >
              {t('billing.currentPlan')}
            </Button>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              {t('billing.currentPlanHint')}
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Button
              type="button"
              className="w-full"
              onClick={() => onChoose(plan)}
              disabled={checkoutDisabled || checkoutPending}
              data-testid="billing-plan-cta"
            >
              {t('billing.choosePlan')}
            </Button>
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              {t('billing.choosePlanHint')}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
