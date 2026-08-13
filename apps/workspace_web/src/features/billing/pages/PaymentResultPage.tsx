import { useEffect, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
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
import { consumePaymentReturn } from '@/app/router/guards';
import { usePurchase, useInvalidateBilling } from '../hooks/useBillingQueries';
import { billingContinuePath, PAYMENT_NOTICE_STATE_KEY, paymentNoticeFromStatus } from '../lib/outcome';

export function PaymentResultPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const purchaseId = params.get('purchase');
  const query = usePurchase(purchaseId);
  const invalidate = useInvalidateBilling();
  const redirected = useRef(false);

  const purchase = query.data;

  useEffect(() => {
    if (!purchase || redirected.current) return;
    redirected.current = true;
    consumePaymentReturn();
    if (purchase.status === 'paid') {
      void invalidate();
    }
    navigate(billingContinuePath(purchase.kind), {
      replace: true,
      state: { [PAYMENT_NOTICE_STATE_KEY]: paymentNoticeFromStatus(purchase.status) },
    });
  }, [purchase, invalidate, navigate]);

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-3xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('billing.eyebrow')} />

      {!purchaseId ? (
        <Card data-testid="billing-payment-missing" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('billing.paymentMissing')}</CardTitle>
            <CardDescription>{t('billing.paymentMissingHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/billing/subscription">{t('billing.continueToSubscription')}</Link>
            </Button>
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

      {purchaseId && !query.isError ? (
        <Card data-testid="billing-payment-loading" className="shadow-xs">
          <CardContent className="p-6 space-y-3">
            <div className="h-3 w-24 rounded bg-muted animate-pulse" />
            <div className="h-7 w-48 rounded bg-muted animate-pulse" />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
