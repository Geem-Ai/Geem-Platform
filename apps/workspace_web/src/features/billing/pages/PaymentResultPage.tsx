import { useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
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
import { formatPeriodDateTime } from '@/features/usage/lib/quota';
import { usePurchase, useInvalidateBilling } from '../hooks/useBillingQueries';
import { PurchaseStatusBadge } from '../components/PurchaseStatusBadge';
import { formatMoney } from '../lib/money';
import { purchaseKindLabelKey } from '../lib/status';
import { isFailedStatus, isPaidStatus, isPendingStatus } from '../lib/status';

export function PaymentResultPage() {
  const { t, i18n } = useTranslation();
  const [params] = useSearchParams();
  const purchaseId = params.get('purchase');
  const query = usePurchase(purchaseId);
  const invalidate = useInvalidateBilling();
  const invalidated = useRef(false);

  const purchase = query.data;

  useEffect(() => {
    if (purchase?.status === 'paid' && !invalidated.current) {
      invalidated.current = true;
      void invalidate();
    }
  }, [purchase?.status, invalidate]);

  const paid = purchase ? isPaidStatus(purchase.status) : false;
  const failed = purchase ? isFailedStatus(purchase.status) : false;
  const pending = purchase ? isPendingStatus(purchase.status) : false;

  const titleKey = paid
    ? 'billing.paymentSuccessTitle'
    : failed
      ? 'billing.paymentFailedTitle'
      : pending
        ? 'billing.paymentPendingTitle'
        : 'billing.paymentUnknownTitle';

  const retryTo =
    purchase?.kind === 'credit_pack' ? '/billing/credits' : '/billing/subscription';

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-3xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t(titleKey)} />
      <div className="space-y-1">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          {t('billing.eyebrow')}
        </p>
        <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{t(titleKey)}</h1>
      </div>

      {!purchaseId ? (
        <Card data-testid="billing-payment-missing" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('billing.paymentMissing')}</CardTitle>
            <CardDescription>{t('billing.paymentMissingHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/billing/subscription">{t('billing.backToBilling')}</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {purchaseId && query.isLoading ? (
        <Card data-testid="billing-payment-loading" className="shadow-xs">
          <CardContent className="p-6 space-y-3">
            <div className="h-3 w-24 rounded bg-muted animate-pulse" />
            <div className="h-7 w-48 rounded bg-muted animate-pulse" />
          </CardContent>
        </Card>
      ) : null}

      {purchaseId && query.isError ? (
        <Card data-testid="billing-payment-error" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('billing.loadError')}</CardTitle>
            <CardDescription>{t('billing.loadErrorHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={() => void query.refetch()}>
              {t('billing.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {purchase ? (
        <Card
          data-testid="billing-payment-result"
          data-status={purchase.status}
          className="shadow-xs overflow-hidden"
        >
          {paid ? <div className="h-0.5 bg-primary" aria-hidden /> : null}
          <CardContent className="p-5 sm:p-6 space-y-5">
            <div className="flex flex-wrap items-center gap-2.5">
              <PurchaseStatusBadge status={purchase.status} testId="billing-payment-status" />
              <p className="text-sm text-muted-foreground">
                {t(purchaseKindLabelKey(purchase.kind))}
              </p>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {paid
                ? t('billing.paymentSuccessHint')
                : failed
                  ? t('billing.paymentFailedHint')
                  : pending
                    ? t('billing.paymentPendingHint')
                    : t('billing.paymentUnknownHint')}
            </p>
            <dl className="space-y-3 text-sm">
              {purchase.item_name ? (
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{t('billing.purchasedItem')}</dt>
                  <dd className="font-medium text-end" data-testid="billing-payment-item">
                    {purchase.item_name}
                  </dd>
                </div>
              ) : null}
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">{t('billing.amount')}</dt>
                <dd className="font-medium tabular-nums">
                  {formatMoney(purchase.amount, purchase.currency)}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">{t('billing.reference')}</dt>
                <dd className="font-mono text-xs text-end break-all">{purchase.id}</dd>
              </div>
              {purchase.paid_at ? (
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">{t('billing.paidAt')}</dt>
                  <dd className="font-medium tabular-nums">
                    {formatPeriodDateTime(purchase.paid_at, i18n.language)}
                  </dd>
                </div>
              ) : null}
            </dl>
            <div className="flex flex-wrap gap-2">
              {paid && purchase.kind === 'subscription' ? (
                <>
                  <Button asChild>
                    <Link to="/billing/subscription">{t('billing.viewSubscription')}</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to="/billing/usage">{t('billing.viewUsage')}</Link>
                  </Button>
                </>
              ) : null}
              {paid && purchase.kind === 'credit_pack' ? (
                <>
                  <Button asChild>
                    <Link to="/billing/credits">{t('billing.viewCredits')}</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to="/billing/usage">{t('billing.viewUsage')}</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to="/chat">{t('billing.backToChat')}</Link>
                  </Button>
                </>
              ) : null}
              {failed ? (
                <>
                  <Button asChild>
                    <Link to={retryTo}>{t('billing.tryAgain')}</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to="/billing/history">{t('billing.backToBilling')}</Link>
                  </Button>
                </>
              ) : null}
              {pending ? (
                <Button asChild variant="outline">
                  <Link to="/billing/history">{t('billing.backToBilling')}</Link>
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
