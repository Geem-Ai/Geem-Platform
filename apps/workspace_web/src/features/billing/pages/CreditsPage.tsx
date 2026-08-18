import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Coins } from 'lucide-react';
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
import { useUsageSummary } from '@/features/usage/hooks/useUsageQueries';
import { formatCount } from '@/features/usage/lib/quota';
import type { CreditPack } from '@/services/api/billing';
import { ApiError } from '@/services/api/errors';
import { BillingPageHeader } from '../components/BillingPageHeader';
import { PaymentOutcomeDialog } from '../components/PaymentOutcomeDialog';
import { CheckoutConfirmDialog } from '../components/CheckoutConfirmDialog';
import { CreditPackCard } from '../components/CreditPackCard';
import { MoneyAmount } from '../components/MoneyAmount';
import { useCreditPackCheckout, useCreditPacks } from '../hooks/useBillingQueries';

function PageSkeleton() {
  return (
    <div className="space-y-6" data-testid="billing-credits-loading">
      <Card className="shadow-xs">
        <CardContent className="p-6 space-y-3">
          <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          <div className="h-7 w-32 rounded bg-muted animate-pulse" />
        </CardContent>
      </Card>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i} className="shadow-xs">
            <CardContent className="p-5 space-y-3">
              <div className="h-4 w-1/2 rounded bg-muted animate-pulse" />
              <div className="h-7 w-1/3 rounded bg-muted animate-pulse" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function CreditsPage() {
  const { t, i18n } = useTranslation();
  const summaryQuery = useUsageSummary();
  const packsQuery = useCreditPacks();
  const checkout = useCreditPackCheckout();
  const [selected, setSelected] = useState<CreditPack | null>(null);

  const loading = summaryQuery.isLoading || packsQuery.isLoading;
  const error = summaryQuery.isError || packsQuery.isError;
  const packs = packsQuery.data ?? [];
  const balance = summaryQuery.data?.credits.balance ?? 0;

  function retry() {
    void summaryQuery.refetch();
    void packsQuery.refetch();
  }

  const gatewayUnavailable =
    checkout.error instanceof ApiError &&
    checkout.error.code === 'billing_gateway_unavailable';

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('billing.creditsTitle')} />
      <PaymentOutcomeDialog />
      <BillingPageHeader
        eyebrow={t('billing.eyebrow')}
        title={t('billing.creditsTitle')}
        description={t('billing.creditsDescription')}
        onRefresh={retry}
        refreshing={summaryQuery.isFetching || packsQuery.isFetching}
      />

      {loading ? <PageSkeleton /> : null}

      {error && !loading ? (
        <Card data-testid="billing-credits-error" className="shadow-xs">
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

          <Card data-testid="billing-credit-balance" className="shadow-xs">
            <CardHeader className="min-h-14">
              <div className="flex items-center gap-2.5">
                <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                  <Coins className="size-3.5" aria-hidden />
                </div>
                <CardTitle className="text-sm">{t('usage.credits')}</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="text-xs text-muted-foreground">{t('usage.creditsBalance')}</p>
                <p
                  className="text-2xl font-semibold tabular-nums tracking-tight mt-1"
                  data-testid="billing-credits-balance"
                >
                  {formatCount(balance, i18n.language)}
                </p>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {t('billing.creditsBalanceHint')}
              </p>
              <Button variant="outline" size="sm" asChild>
                <Link to="/billing/usage">{t('billing.viewUsage')}</Link>
              </Button>
            </CardContent>
          </Card>

          <section className="space-y-3">
            <div>
              <h2 className="text-sm font-semibold tracking-tight">
                {t('billing.availablePacks')}
              </h2>
              <p className="text-xs text-muted-foreground mt-1">
                {t('billing.availablePacksHint')}
              </p>
            </div>
            {packs.length === 0 ? (
              <Card data-testid="billing-packs-empty" className="shadow-xs">
                <CardContent className="p-8 text-center text-sm text-muted-foreground">
                  {t('billing.packsEmpty')}
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {packs.map((pack) => (
                  <CreditPackCard
                    key={pack.id}
                    pack={pack}
                    checkoutDisabled={gatewayUnavailable}
                    checkoutPending={checkout.isPending}
                    onBuy={(next) => {
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
        title={t('billing.confirmPackTitle')}
        description={t('billing.confirmPackHint')}
        rows={
          selected
            ? [
                { label: t('billing.pack'), value: selected.name },
                {
                  label: t('billing.creditsAmount'),
                  value: t('billing.packCredits', {
                    count: formatCount(selected.credits, i18n.language),
                  }),
                },
                {
                  label: t('billing.price'),
                  value: (
                    <MoneyAmount
                      amount={selected.price_amount}
                      currency={selected.currency}
                    />
                  ),
                },
              ]
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
