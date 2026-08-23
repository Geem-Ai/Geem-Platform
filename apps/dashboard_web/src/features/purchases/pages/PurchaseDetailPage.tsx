import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Download, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { PurchaseStatusBadge } from '@/components/shared/StatusBadges';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  PurchaseProductCell,
  PurchaseWorkspaceCell,
} from '@/features/purchases/components/PurchaseTableCells';
import { purchaseKindLabel } from '@/features/purchases/lib/labels';
import { formatAdminDate } from '@/lib/dates';
import { formatMoney } from '@/lib/format';
import { getErrorMessage } from '@/services/api/errors';
import {
  downloadPlatformPurchaseInvoice,
  fetchPlatformPurchase,
  platformQueryKeys,
  reconcilePlatformPurchase,
} from '@/services/api/platform';

export function PurchaseDetailPage() {
  const { purchaseId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [reconcileOpen, setReconcileOpen] = useState(false);

  const query = useQuery({
    queryKey: platformQueryKeys.purchase(purchaseId),
    queryFn: () => fetchPlatformPurchase(purchaseId),
    enabled: Boolean(purchaseId),
  });

  const reconcileMutation = useMutation({
    mutationFn: () => reconcilePlatformPurchase(purchaseId),
    onSuccess: (result) => {
      setReconcileOpen(false);
      if (result.idempotent_replay) {
        toast.message(t('purchases.reconcileAlreadyPaid'));
      } else if (result.fulfillment_applied) {
        toast.success(t('purchases.reconcileSuccess'));
      } else if (result.resulting_status === 'paid') {
        toast.success(t('purchases.reconcileSuccess'));
      } else {
        toast.message(t('purchases.reconcileNoChange'));
      }
      void queryClient.invalidateQueries({ queryKey: platformQueryKeys.purchase(purchaseId) });
      void queryClient.invalidateQueries({ queryKey: ['platform', 'purchases'] });
    },
    onError: (err) => {
      const message = getErrorMessage(err, t);
      if (message.toLowerCase().includes('unavailable') || message.toLowerCase().includes('timeout')) {
        toast.error(t('purchases.reconcileUnavailable'));
      } else {
        toast.error(message);
      }
    },
  });

  const purchase = query.data;

  const handleInvoiceDownload = async () => {
    try {
      const blob = await downloadPlatformPurchaseInvoice(purchaseId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${purchase?.fulfillment.invoice_number || purchaseId}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(getErrorMessage(err, t));
    }
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[960px] flex-col gap-6 p-5 md:p-8"
      data-testid="purchase-detail-page"
    >
      <DocumentTitle title={t('purchases.detailTitle')} />

      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/purchases">
            <ArrowLeft className="size-4" aria-hidden />
            {t('purchases.title')}
          </Link>
        </Button>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}>
          <RefreshCw className="size-4" aria-hidden />
          {t('common.refresh')}
        </Button>
      </div>

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : query.isError || !purchase ? (
        <p className="text-sm text-destructive">{getErrorMessage(query.error, t)}</p>
      ) : (
        <>
          <section className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{t('purchases.detailTitle')}</h1>
              <PurchaseStatusBadge status={purchase.status} />
            </div>
            <p className="font-mono text-xs text-muted-foreground break-all">{purchase.id}</p>
          </section>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('purchases.overview')}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-muted-foreground">{t('purchases.workspace')}</p>
                <PurchaseWorkspaceCell workspace={purchase.workspace} />
              </div>
              <div>
                <p className="text-muted-foreground">{t('nav.users')}</p>
                <p>{purchase.actor.email}</p>
              </div>
              <div>
                <p className="text-muted-foreground">{t('purchases.amount')}</p>
                <p>{formatMoney(purchase.amount, purchase.currency)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">{t('purchases.created')}</p>
                <p>{formatAdminDate(purchase.created_at, i18n.language)}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('purchases.product')}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <PurchaseProductCell kind={purchase.kind} target={purchase.target} />
              <p className="text-muted-foreground">{purchaseKindLabel(t, purchase.kind)}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('purchases.payment')}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-muted-foreground">{t('purchases.gateway')}</p>
                <p>{purchase.gateway.display_name}</p>
              </div>
              <div>
                <p className="text-muted-foreground">cart_id</p>
                <p className="font-mono text-xs break-all">{purchase.gateway.cart_id}</p>
              </div>
              <div>
                <p className="text-muted-foreground">tran_ref</p>
                <p className="font-mono text-xs break-all">{purchase.gateway.tran_ref ?? '—'}</p>
              </div>
              <div>
                <p className="text-muted-foreground">provider_status</p>
                <p>{purchase.gateway.provider_status ?? '—'}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('purchases.fulfillment')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p>
                {purchase.fulfillment.fulfilled
                  ? t('purchases.fulfilled')
                  : t('purchases.notFulfilled')}
              </p>
              {purchase.fulfillment.invoice_available ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleInvoiceDownload()}
                  data-testid="purchase-download-invoice"
                >
                  <Download className="size-4" aria-hidden />
                  {t('purchases.downloadInvoice')}
                </Button>
              ) : (
                <p className="text-muted-foreground">{t('purchases.invoiceUnavailable')}</p>
              )}
            </CardContent>
          </Card>

          {purchase.reconcile_eligible ? (
            <Button onClick={() => setReconcileOpen(true)} data-testid="purchase-reconcile-button">
              {t('purchases.reconcile')}
            </Button>
          ) : null}
        </>
      )}

      <AlertDialog open={reconcileOpen} onOpenChange={setReconcileOpen}>
        <AlertDialogContent data-testid="purchase-reconcile-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('purchases.reconcileTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('purchases.reconcileDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={reconcileMutation.isPending}>
              {t('common.cancel')}
            </AlertDialogCancel>
            <Button
              disabled={reconcileMutation.isPending}
              onClick={() => reconcileMutation.mutate()}
              data-testid="purchase-reconcile-confirm"
            >
              {reconcileMutation.isPending ? t('common.working') : t('purchases.reconcileConfirm')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
