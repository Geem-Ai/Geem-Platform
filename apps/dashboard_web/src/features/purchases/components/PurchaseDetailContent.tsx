import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  ArrowUpRight,
  Check,
  CheckCircle2,
  CircleAlert,
  CircleX,
  Clock3,
  Copy,
  CreditCard,
  Download,
  FileText,
  LoaderCircle,
  Package,
  ReceiptText,
  RefreshCw,
  ShoppingCart,
  UserRound,
  type LucideIcon,
} from 'lucide-react';
import { toast } from 'sonner';
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  SheetBody,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  PurchaseProductCell,
  PurchaseWorkspaceCell,
} from '@/features/purchases/components/PurchaseTableCells';
import { purchaseKindLabel } from '@/features/purchases/lib/labels';
import { formatAdminDateTime } from '@/lib/dates';
import { formatInteger, formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  downloadPlatformPurchaseInvoice,
  fetchPlatformPurchase,
  platformQueryKeys,
  reconcilePlatformPurchase,
} from '@/services/api/platform';

type PurchaseDetailContentProps = {
  purchaseId: string;
  onClose: () => void;
};

export function PurchaseDetailContent({ purchaseId, onClose }: PurchaseDetailContentProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [reconcileOpen, setReconcileOpen] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const query = useQuery({
    queryKey: platformQueryKeys.purchase(purchaseId),
    queryFn: () => fetchPlatformPurchase(purchaseId),
    enabled: Boolean(purchaseId),
  });

  const reconcileMutation = useMutation({
    mutationFn: () => reconcilePlatformPurchase(purchaseId),
    onSuccess: (result) => {
      setReconcileOpen(false);
      queryClient.setQueryData(platformQueryKeys.purchase(purchaseId), result.purchase);
      if (result.idempotent_replay) {
        toast.message(t('purchases.reconcileAlreadyPaid'));
      } else if (result.fulfillment_applied || result.resulting_status === 'paid') {
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
    if (isDownloading) return;

    setIsDownloading(true);
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
    } finally {
      setIsDownloading(false);
    }
  };

  const activityItems = purchase
    ? [
        {
          key: 'created',
          icon: ShoppingCart,
          label: t('purchases.created'),
          value: formatAdminDateTime(purchase.created_at, i18n.language),
        },
        ...(purchase.paid_at
          ? [
              {
                key: 'paid',
                icon: CheckCircle2,
                label: t('purchases.paidAt'),
                value: formatAdminDateTime(purchase.paid_at, i18n.language),
              },
            ]
          : []),
        {
          key: 'updated',
          icon: Clock3,
          label: t('purchases.updated'),
          value: formatAdminDateTime(purchase.updated_at, i18n.language),
        },
      ]
    : [];

  return (
    <>
      <SheetHeader className="border-b border-border px-5 py-4 pe-13 text-start">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <ReceiptText className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <SheetTitle className="truncate text-base font-semibold">
                {t('purchases.drawerTitle')}
              </SheetTitle>
              <SheetDescription className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs">
                {purchase ? (
                  <>
                    <span className="truncate">{purchaseKindLabel(t, purchase.kind)}</span>
                    <span aria-hidden>·</span>
                    <bdi dir="ltr" className="shrink-0 font-medium text-foreground">
                      {formatMoney(purchase.amount, purchase.currency)}
                    </bdi>
                  </>
                ) : (
                  <>
                    <span>{t('purchases.purchaseId')}</span>
                    <bdi dir="ltr" className="truncate font-mono">
                      {purchaseId}
                    </bdi>
                  </>
                )}
              </SheetDescription>
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            mode="icon"
            size="sm"
            className="shrink-0"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
            aria-label={t('common.refresh')}
            title={t('common.refresh')}
          >
            <RefreshCw className={cn('size-3.5', query.isFetching && 'animate-spin')} aria-hidden />
          </Button>
        </div>
      </SheetHeader>

      <SheetBody className="min-h-0 grow p-0">
        <ScrollArea className="h-full">
          {query.isLoading ? <PurchaseDetailSkeleton label={t('purchases.loadingDetails')} /> : null}

          {query.isError || (!query.isLoading && !purchase) ? (
            <div
              className="flex min-h-[28rem] flex-col items-center justify-center px-6 py-12 text-center"
              role="alert"
              data-testid="purchase-detail-error"
            >
              <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <CircleAlert className="size-5" aria-hidden />
              </span>
              <h2 className="text-base font-semibold">{t('purchases.detailErrorTitle')}</h2>
              <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
                {getErrorMessage(query.error, t)}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-5"
                onClick={() => void query.refetch()}
              >
                <RefreshCw className="size-3.5" aria-hidden />
                {t('common.retry')}
              </Button>
            </div>
          ) : null}

          {purchase ? (
            <div
              className="space-y-5 p-5"
              data-testid="purchase-detail-content"
            >
              <section className="relative overflow-hidden rounded-2xl border border-primary/15 bg-linear-to-br from-primary/[0.1] via-card to-card p-5">
                <div className="pointer-events-none absolute -end-14 -top-16 size-40 rounded-full bg-primary/10 blur-3xl" />
                <div className="relative">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary rtl:tracking-normal">
                      {t('purchases.total')}
                    </p>
                    <PurchaseStatusBadge status={purchase.status} />
                  </div>
                  <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
                    <bdi dir="ltr">{formatMoney(purchase.amount, purchase.currency)}</bdi>
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Badge variant="secondary" appearance="light" size="sm">
                      {purchaseKindLabel(t, purchase.kind)}
                    </Badge>
                    {purchase.fulfillment.invoice_available ? (
                      <Badge variant="success" appearance="light" size="sm">
                        <FileText className="size-3" aria-hidden />
                        {t('purchases.invoiceAvailable')}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-5 border-t border-primary/10 pt-4">
                    <p className="text-xs font-medium text-muted-foreground">
                      {t('purchases.purchaseId')}
                    </p>
                    <CopyableValue
                      label={t('purchases.purchaseId')}
                      value={purchase.id}
                      className="mt-1.5 bg-background/70"
                    />
                  </div>
                </div>
              </section>

              <DetailSection icon={Package} title={t('purchases.overview')}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <EntityTile label={t('purchases.workspace')}>
                    <PurchaseWorkspaceCell workspace={purchase.workspace} />
                  </EntityTile>
                  <EntityTile label={t('purchases.buyer')}>
                    <Link
                      to={`/users/${purchase.actor.id}`}
                      className="group flex min-w-0 items-center gap-2.5 rounded-md focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <UserRound className="size-4" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium group-hover:text-primary group-hover:underline">
                        <bdi dir="ltr">{purchase.actor.email}</bdi>
                      </span>
                      <ArrowUpRight className="size-3.5 shrink-0 text-muted-foreground rtl:-scale-x-100" aria-hidden />
                    </Link>
                  </EntityTile>
                </div>

                <div className="border-t border-border pt-4">
                  <p className="text-xs font-medium text-muted-foreground">
                    {t('purchases.product')}
                  </p>
                  <div className="mt-2">
                    <PurchaseProductCell kind={purchase.kind} target={purchase.target} />
                  </div>
                  {purchase.target.item_code || purchase.target.credits != null ? (
                    <dl className="mt-4 grid gap-4 sm:grid-cols-2">
                      {purchase.target.item_code ? (
                        <DefinitionItem
                          label={t('purchases.itemCode')}
                          value={
                            <bdi dir="ltr" className="font-mono text-xs">
                              {purchase.target.item_code}
                            </bdi>
                          }
                        />
                      ) : null}
                      {purchase.target.credits != null ? (
                        <DefinitionItem
                          label={t('purchases.credits')}
                          value={formatInteger(purchase.target.credits, i18n.language)}
                        />
                      ) : null}
                    </dl>
                  ) : null}
                </div>
              </DetailSection>

              <DetailSection icon={CreditCard} title={t('purchases.payment')}>
                <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 p-3.5">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300">
                    <CreditCard className="size-4.5" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{purchase.gateway.display_name}</p>
                    <p className="mt-0.5 font-mono text-xs text-muted-foreground">
                      <bdi dir="ltr">{purchase.gateway.code}</bdi>
                    </p>
                  </div>
                  {purchase.gateway.provider_status ? (
                    <Badge variant="secondary" appearance="light" size="sm" className="max-w-40 truncate">
                      {purchase.gateway.provider_status}
                    </Badge>
                  ) : null}
                </div>

                <dl className="grid gap-x-5 gap-y-4 sm:grid-cols-2">
                  <DefinitionItem
                    label={t('purchases.cartId')}
                    value={<CopyableValue label={t('purchases.cartId')} value={purchase.gateway.cart_id} />}
                  />
                  <DefinitionItem
                    label={t('purchases.transactionReference')}
                    value={
                      <CopyableValue
                        label={t('purchases.transactionReference')}
                        value={purchase.gateway.tran_ref}
                      />
                    }
                  />
                  <DefinitionItem
                    label={t('purchases.gatewayConfigId')}
                    value={
                      <CopyableValue
                        label={t('purchases.gatewayConfigId')}
                        value={purchase.gateway.gateway_config_id}
                      />
                    }
                  />
                  <DefinitionItem
                    label={t('purchases.lastQueryStatus')}
                    value={purchase.gateway.last_query_status ?? '—'}
                  />
                </dl>
              </DetailSection>

              <DetailSection icon={FileText} title={t('purchases.fulfillment')}>
                <div
                  className={cn(
                    'flex items-start gap-3 rounded-xl border p-4',
                    purchase.fulfillment.fulfilled
                      ? 'border-green-200 bg-green-50/70 dark:border-green-900 dark:bg-green-950/35'
                      : 'border-amber-200 bg-amber-50/70 dark:border-amber-900 dark:bg-amber-950/35',
                  )}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full',
                      purchase.fulfillment.fulfilled
                        ? 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
                    )}
                  >
                    {purchase.fulfillment.fulfilled ? (
                      <CheckCircle2 className="size-4" aria-hidden />
                    ) : (
                      <CircleX className="size-4" aria-hidden />
                    )}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">
                      {purchase.fulfillment.fulfilled
                        ? t('purchases.fulfilled')
                        : t('purchases.notFulfilled')}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {purchase.fulfillment.fulfilled
                        ? t('purchases.fulfilledDescription')
                        : t('purchases.notFulfilledDescription')}
                    </p>
                  </div>
                </div>

                <dl className="grid gap-4 sm:grid-cols-2">
                  <DefinitionItem
                    label={t('purchases.invoice')}
                    value={
                      purchase.fulfillment.invoice_available
                        ? t('purchases.invoiceAvailable')
                        : t('purchases.invoiceUnavailable')
                    }
                  />
                  <DefinitionItem
                    label={t('purchases.invoiceNumber')}
                    value={
                      <CopyableValue
                        label={t('purchases.invoiceNumber')}
                        value={purchase.fulfillment.invoice_number}
                      />
                    }
                  />
                </dl>
              </DetailSection>

              <DetailSection icon={Clock3} title={t('purchases.activity')}>
                <ol>
                  {activityItems.map((item, index) => (
                    <ActivityItem
                      key={item.key}
                      icon={item.icon}
                      label={item.label}
                      value={item.value}
                      last={index === activityItems.length - 1}
                    />
                  ))}
                </ol>
              </DetailSection>
            </div>
          ) : null}
        </ScrollArea>
      </SheetBody>

      <SheetFooter className="flex-col-reverse items-stretch gap-2 border-t border-border p-4 sm:flex-row sm:items-center sm:justify-between sm:space-x-0">
        <Button
          type="button"
          variant="outline"
          onClick={onClose}
          data-testid="purchase-detail-close"
        >
          {t('common.close')}
        </Button>
        {purchase && (purchase.fulfillment.invoice_available || purchase.reconcile_eligible) ? (
          <div className="grid gap-2 sm:flex sm:items-center">
            {purchase.fulfillment.invoice_available ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleInvoiceDownload()}
                disabled={isDownloading}
                data-testid="purchase-download-invoice"
              >
                {isDownloading ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Download className="size-4" aria-hidden />
                )}
                {t('purchases.downloadInvoice')}
              </Button>
            ) : null}
            {purchase.reconcile_eligible ? (
              <Button
                type="button"
                onClick={() => setReconcileOpen(true)}
                data-testid="purchase-reconcile-button"
              >
                <RefreshCw className="size-4" aria-hidden />
                {t('purchases.reconcile')}
              </Button>
            ) : null}
          </div>
        ) : null}
      </SheetFooter>

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
              type="button"
              disabled={reconcileMutation.isPending}
              onClick={() => reconcileMutation.mutate()}
              data-testid="purchase-reconcile-confirm"
            >
              {reconcileMutation.isPending ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : null}
              {reconcileMutation.isPending ? t('common.working') : t('purchases.reconcileConfirm')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function DetailSection({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2.5 border-b border-border bg-muted/20 px-4 py-3">
        <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-3.5" aria-hidden />
        </span>
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      <div className="space-y-4 p-4">{children}</div>
    </section>
  );
}

function EntityTile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-muted/25 p-3.5">
      <p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>
      {children}
    </div>
  );
}

function DefinitionItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1.5 min-w-0 break-words text-sm font-medium">{value}</dd>
    </div>
  );
}

function CopyableValue({
  label,
  value,
  className,
}: {
  label: string;
  value?: string | null;
  className?: string;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  if (!value) return <span className="text-muted-foreground">—</span>;

  const copyValue = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(t('purchases.copySuccess', { label }));
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      toast.error(t('purchases.copyError'));
    }
  };

  const buttonLabel = copied
    ? t('purchases.copiedLabel', { label })
    : t('purchases.copyLabel', { label });

  return (
    <span
      className={cn(
        'flex min-w-0 items-center gap-1 rounded-md bg-muted/60 py-1 ps-2 pe-1',
        className,
      )}
    >
      <bdi dir="ltr" className="min-w-0 flex-1 break-all font-mono text-xs font-normal">
        {value}
      </bdi>
      <Button
        type="button"
        variant="ghost"
        mode="icon"
        size="sm"
        className="shrink-0"
        onClick={() => void copyValue()}
        aria-label={buttonLabel}
        title={buttonLabel}
      >
        {copied ? (
          <Check className="size-3.5 text-green-600" aria-hidden />
        ) : (
          <Copy className="size-3.5" aria-hidden />
        )}
      </Button>
    </span>
  );
}

function ActivityItem({
  icon: Icon,
  label,
  value,
  last,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  last: boolean;
}) {
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {!last ? (
        <span className="absolute bottom-0 start-[15px] top-8 w-px bg-border" aria-hidden />
      ) : null}
      <span className="relative z-1 flex size-8 shrink-0 items-center justify-center rounded-full border border-border bg-background text-muted-foreground">
        <Icon className="size-3.5" aria-hidden />
      </span>
      <div className="min-w-0 pt-0.5">
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{value}</p>
      </div>
    </li>
  );
}

function PurchaseDetailSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-5 p-5" data-testid="purchase-detail-loading" role="status">
      <span className="sr-only">{label}</span>
      <div className="h-44 animate-pulse rounded-2xl bg-muted" />
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="overflow-hidden rounded-xl border border-border">
          <div className="h-12 animate-pulse border-b border-border bg-muted/60" />
          <div className="space-y-3 p-4">
            <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-10 animate-pulse rounded-lg bg-muted/70" />
            <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}
