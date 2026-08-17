import { useTranslation } from 'react-i18next';
import { Check } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { AppPlan, CatalogApp } from '@/services/api/apps';
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
  const price =
    Number(plan.price_amount) <= 0
      ? t('apps.billing.free')
      : `${plan.currency} ${plan.price_amount}${
          plan.billing_interval === 'monthly' ? ` ${t('apps.billing.perMonth')}` : ''
        }`;

  return (
    <div
      className={`rounded-xl border p-4 space-y-3 ${
        selected ? 'border-primary bg-primary/5' : 'border-border'
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
      </div>
      {localized.description ? (
        <p className="text-sm text-muted-foreground">{localized.description}</p>
      ) : null}
      <p className="text-sm font-medium tabular-nums">{price}</p>
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
