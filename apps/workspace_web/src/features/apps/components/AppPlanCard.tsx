import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { AppPlan, CatalogApp } from '@/services/api/apps';
import { MoneyAmount } from '@/features/billing/components/MoneyAmount';
import {
  formatAppEntitlement,
  localizeAppPlan,
} from '../lib/billing-label';
import { AppPurchaseButton } from './AppPurchaseButton';

export function AppPlanCard({
  app,
  plan,
  canManage,
  selected,
}: {
  app: CatalogApp;
  plan: AppPlan;
  canManage: boolean;
  selected?: boolean;
}) {
  const { t } = useTranslation();
  const localized = localizeAppPlan(plan, t);
  const isCurrent =
    selected ||
    (app.access?.plan_id != null && app.access.plan_id === plan.id) ||
    (app.access?.plan_code != null && app.access.plan_code === plan.code);
  const isFree = Number(plan.price_amount) <= 0;

  return (
    <div
      className={`rounded-xl border p-4 space-y-3 ${
        isCurrent ? 'border-primary bg-primary/5' : 'border-border'
      }`}
      data-testid={`app-plan-${plan.code}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold">{localized.name}</h4>
        {plan.is_default ? (
          <Badge variant="secondary" appearance="light" size="sm">
            {t('apps.defaultPlan')}
          </Badge>
        ) : null}
        {isCurrent && app.access?.commercially_entitled ? (
          <Badge variant="success" appearance="light" size="sm">
            {t('apps.billing.currentPlan')}
          </Badge>
        ) : null}
      </div>
      {localized.description ? (
        <p className="text-sm text-muted-foreground">{localized.description}</p>
      ) : null}
      <p className="text-sm font-medium">
        {isFree ? (
          t('apps.billing.free')
        ) : (
          <span className="inline-flex items-center gap-1 flex-wrap">
            <MoneyAmount amount={plan.price_amount} currency={plan.currency} />
            {plan.billing_interval === 'monthly' ? (
              <span>{t('apps.billing.perMonth')}</span>
            ) : null}
          </span>
        )}
      </p>
      {app.billing_type === 'subscription' ? (
        <p className="text-xs text-muted-foreground">{t('apps.billing.manualRenewal')}</p>
      ) : null}
      {Object.keys(plan.entitlements).length > 0 ? (
        <ul className="space-y-1.5 pt-1">
          {Object.entries(plan.entitlements).map(([key, value]) => (
            <li
              key={key}
              className="flex items-center gap-2 text-sm text-muted-foreground"
            >
              <Check className="size-3.5 text-primary shrink-0" aria-hidden />
              <span>{formatAppEntitlement(key, value, t)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {app.access?.can_purchase ? (
        <AppPurchaseButton app={app} plan={plan} canManage={canManage} />
      ) : null}
    </div>
  );
}
