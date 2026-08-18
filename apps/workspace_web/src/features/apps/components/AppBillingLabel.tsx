import { Trans, useTranslation } from 'react-i18next';
import type { CatalogApp } from '@/services/api/apps';
import { MoneyAmount } from '@/features/billing/components/MoneyAmount';
import { resolveAppBillingLabel } from '../lib/billing-label';

/** Catalog / detail billing line with SAR rendered as the official symbol SVG. */
export function AppBillingLabel({
  app,
}: {
  app: Pick<CatalogApp, 'billing_type' | 'status' | 'plans'>;
}) {
  const { t } = useTranslation();
  const model = resolveAppBillingLabel(app);

  if (model.kind === 'i18n') {
    return <>{t(model.key)}</>;
  }

  const amount = (
    <MoneyAmount amount={model.amount} currency={model.currency} />
  );

  if (model.kind === 'one_time_price') {
    return (
      <Trans
        i18nKey="apps.billing.oneTimePriceRich"
        components={{ amount }}
      />
    );
  }

  return (
    <Trans
      i18nKey="apps.billing.fromMonthlyRich"
      components={{ amount }}
    />
  );
}
