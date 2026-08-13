import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { useEntitlements, useSubscription } from '@/features/usage/hooks/useUsageQueries';
import type { ByteUnitKey } from '@/features/usage/lib/quota';
import type { PurchasablePlan } from '@/services/api/billing';
import { ApiError } from '@/services/api/errors';
import { BillingPageHeader } from '../components/BillingPageHeader';
import { CheckoutConfirmDialog } from '../components/CheckoutConfirmDialog';
import { CurrentSubscriptionCard } from '../components/CurrentSubscriptionCard';
import { PlanCard } from '../components/PlanCard';
import { useBillingPlans, useSubscriptionCheckout } from '../hooks/useBillingQueries';
import {
  entitlementLabelKey,
  formatEntitlementValue,
  isEntitlementI18nValue,
  sortEntitlements,
} from '../lib/entitlements';
import { formatMoney } from '../lib/money';
import { sortPlansForDisplay } from '../lib/plans';

function PageSkeleton() {
  return (
    <div className="space-y-6" data-testid="billing-subscription-loading">
      <Card className="shadow-xs">
        <CardContent className="p-6 space-y-3">
          <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          <div className="h-7 w-48 rounded bg-muted animate-pulse" />
        </CardContent>
      </Card>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="shadow-xs">
            <CardContent className="p-5 space-y-3">
              <div className="h-4 w-1/2 rounded bg-muted animate-pulse" />
              <div className="h-7 w-1/3 rounded bg-muted animate-pulse" />
              <div className="h-2 w-full rounded bg-muted animate-pulse" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function SubscriptionPage() {
  const { t, i18n } = useTranslation();
  const subscriptionQuery = useSubscription();
  const entitlementsQuery = useEntitlements();
  const plansQuery = useBillingPlans();
  const checkout = useSubscriptionCheckout();
  const [selected, setSelected] = useState<PurchasablePlan | null>(null);

  const loading = subscriptionQuery.isLoading || plansQuery.isLoading;
  const error = subscriptionQuery.isError || plansQuery.isError;
  const subscription = subscriptionQuery.data;
  const plans = sortPlansForDisplay(
    plansQuery.data ?? [],
    subscription?.plan.id,
  );
  const catalogPlan = plans.find((plan) => plan.id === subscription?.plan.id);
  const byteUnit = (unit: ByteUnitKey) => t(`usage.units.${unit}`);

  function retry() {
    void subscriptionQuery.refetch();
    void entitlementsQuery.refetch();
    void plansQuery.refetch();
  }

  const gatewayUnavailable =
    checkout.error instanceof ApiError &&
    checkout.error.code === 'billing_gateway_unavailable';

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('billing.subscriptionTitle')} />
      <BillingPageHeader
        eyebrow={t('billing.eyebrow')}
        title={t('billing.subscriptionTitle')}
        description={t('billing.subscriptionDescription')}
        onRefresh={retry}
        refreshing={subscriptionQuery.isFetching || plansQuery.isFetching}
      />

      {loading ? <PageSkeleton /> : null}

      {error && !loading ? (
        <Card data-testid="billing-subscription-error" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('billing.loadError')}</CardTitle>
            <CardDescription>{t('billing.loadErrorHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={retry}>
              {t('billing.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!loading && !error ? (
        <>
          {gatewayUnavailable ? (
            <Card data-testid="billing-gateway-unavailable" className="shadow-xs">
              <CardContent className="p-5 text-sm text-muted-foreground">
                {t('errors.billingGatewayUnavailable')}
              </CardContent>
            </Card>
          ) : null}

          {subscription ? (
            <CurrentSubscriptionCard
              subscription={subscription}
              entitlements={entitlementsQuery.data}
              catalogPlan={catalogPlan}
            />
          ) : null}

          <section className="space-y-3">
            <div>
              <h2 className="text-sm font-semibold tracking-tight">
                {t('billing.availablePlans')}
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                {t('billing.availablePlansHint')}
              </p>
            </div>
            {plans.length === 0 ? (
              <Card data-testid="billing-plans-empty" className="shadow-xs">
                <CardContent className="p-8 text-center text-sm text-muted-foreground">
                  {t('billing.plansEmpty')}
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {plans.map((plan) => (
                  <PlanCard
                    key={plan.id}
                    plan={plan}
                    current={plan.id === subscription?.plan.id}
                    checkoutDisabled={gatewayUnavailable}
                    checkoutPending={checkout.isPending}
                    onChoose={(next) => {
                      checkout.reset();
                      setSelected(next);
                    }}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}

      <CheckoutConfirmDialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelected(null);
            checkout.reset();
          }
        }}
        title={t('billing.confirmPlanTitle')}
        description={t('billing.confirmPlanHint')}
        rows={
          selected
            ? [
                { label: t('billing.plan'), value: selected.name },
                {
                  label: t('billing.price'),
                  value: formatMoney(selected.price_amount, selected.currency),
                },
              ]
            : []
        }
        features={
          selected
            ? sortEntitlements(selected.entitlements).map((item) => {
                const formatted = formatEntitlementValue(
                  item,
                  i18n.language,
                  byteUnit,
                );
                const value = isEntitlementI18nValue(formatted)
                  ? t(formatted)
                  : formatted;
                return {
                  label: t(entitlementLabelKey(item.key), { key: item.key }),
                  value,
                };
              })
            : []
        }
        pending={checkout.isPending}
        error={checkout.error}
        onConfirm={() => {
          if (selected) checkout.mutate(selected.id);
        }}
      />
    </div>
  );
}
