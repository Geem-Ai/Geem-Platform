import { useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
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
import { usePurchase, useInvalidateBilling } from '@/features/billing/hooks/useBillingQueries';
import { isFailedStatus, isPaidStatus } from '@/features/billing/lib/status';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { useApp, invalidateAppsCache } from '../hooks/useAppsQueries';

function formatDate(value: string | null | undefined, locale: string): string {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: 'long' }).format(new Date(value));
  } catch {
    return value;
  }
}

export function AppPaymentResultPage() {
  const { t, i18n } = useTranslation();
  const [params] = useSearchParams();
  const purchaseId = params.get('purchase');
  const query = usePurchase(purchaseId);
  const invalidateBilling = useInvalidateBilling();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const purchase = query.data;
  const paid = Boolean(purchase && isPaidStatus(purchase.status));
  const appSlug = purchase?.app_slug ?? undefined;
  const appQuery = useApp(appSlug, paid && Boolean(appSlug));
  const periodEnd = appQuery.data?.access?.current_period_end;

  useEffect(() => {
    if (!purchase) return;
    consumePaymentReturn();
    if (isPaidStatus(purchase.status)) {
      void invalidateBilling();
      void invalidateAppsCache(queryClient, workspaceId, purchase.app_slug ?? undefined);
    }
  }, [purchase, invalidateBilling, queryClient, workspaceId]);

  const appName = purchase?.app_name || purchase?.item_name || t('apps.title');
  const manageHref = appSlug ? `/apps/${appSlug}` : '/apps';
  const periodLabel = formatDate(periodEnd, i18n.language);

  let title = t('apps.payment.pendingTitle');
  let hint = t('apps.payment.pendingHint');
  let testId = 'app-payment-pending';

  if (purchase && isPaidStatus(purchase.status)) {
    if (purchase.kind === 'app_one_time') {
      title = t('apps.payment.successTitle');
      hint = t('apps.payment.oneTimeSuccess', { name: appName });
    } else if (purchase.kind === 'app_subscription_renewal') {
      title = t('apps.payment.renewalSuccessTitle');
      hint = periodLabel
        ? t('apps.payment.renewalSuccess', { name: appName, date: periodLabel })
        : t('apps.payment.renewalSuccessFallback', { name: appName });
    } else {
      title = t('apps.payment.subscriptionSuccessTitle');
      hint = periodLabel
        ? t('apps.payment.subscriptionSuccess', { name: appName, date: periodLabel })
        : t('apps.payment.subscriptionSuccessFallback', { name: appName });
    }
    testId = 'app-payment-success';
  } else if (purchase && isFailedStatus(purchase.status)) {
    title = t('apps.payment.failedTitle');
    hint = t('apps.payment.failedHint');
    testId = 'app-payment-failed';
  }

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-3xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('apps.title')} />

      {!purchaseId ? (
        <Card data-testid="app-payment-missing" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('apps.payment.missingTitle')}</CardTitle>
            <CardDescription>{t('apps.payment.missingHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/apps">{t('apps.backToStore')}</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {purchaseId && query.isError ? (
        <Card data-testid="app-payment-error" className="shadow-xs">
          <CardHeader>
            <CardTitle>{t('apps.loadError')}</CardTitle>
            <CardDescription>{t('apps.payment.errorHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={() => void query.refetch()}>
              {t('apps.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {purchaseId && query.isLoading ? (
        <Card data-testid="app-payment-loading" className="shadow-xs">
          <CardContent className="p-6 space-y-3">
            <div className="h-3 w-24 rounded bg-muted animate-pulse" />
            <div className="h-7 w-48 rounded bg-muted animate-pulse" />
          </CardContent>
        </Card>
      ) : null}

      {purchase ? (
        <Card data-testid={testId} className="shadow-xs">
          <CardHeader>
            <CardTitle>{title}</CardTitle>
            <CardDescription data-testid="app-payment-hint">{hint}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {purchase.item_name ? (
              <p className="text-sm text-muted-foreground">{purchase.item_name}</p>
            ) : null}
            <p className="text-sm tabular-nums">
              {purchase.currency} {purchase.amount}
            </p>
            {purchase.paid_at && isPaidStatus(purchase.status) ? (
              <p className="text-sm text-muted-foreground">
                {formatDate(purchase.paid_at, i18n.language)}
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button asChild>
                <Link to={manageHref}>
                  {purchase.kind === 'app_one_time'
                    ? t('apps.payment.openApp')
                    : t('apps.payment.manageApp')}
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/apps">{t('apps.backToStore')}</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
