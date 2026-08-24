import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Receipt, RefreshCw, SearchX } from 'lucide-react';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { PurchaseStatusBadge } from '@/components/shared/StatusBadges';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Sheet, SheetContent, floatingSheetPanel } from '@/components/ui/sheet';
import { PurchaseDetailContent } from '@/features/purchases/components/PurchaseDetailContent';
import {
  PurchaseProductCell,
  PurchaseWorkspaceCell,
} from '@/features/purchases/components/PurchaseTableCells';
import { purchaseKindLabel } from '@/features/purchases/lib/labels';
import { formatAdminDate } from '@/lib/dates';
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformPurchases, platformQueryKeys } from '@/services/api/platform';

const PAGE_SIZE = 25;

const STATUS_OPTIONS = [
  'pending',
  'redirected',
  'paid',
  'failed',
  'cancelled',
  'expired',
] as const;

const KIND_OPTIONS = [
  'subscription',
  'credit_pack',
  'app_one_time',
  'app_subscription',
  'app_subscription_renewal',
] as const;

const GATEWAY_OPTIONS = ['noop', 'clickpay'] as const;

const PURCHASE_DETAIL_PANEL = floatingSheetPanel(
  'w-[calc(100%-2.5rem)]',
  'sm:w-[min(100%-2.5rem,38rem)]',
  'lg:w-[42rem]',
);

export function PurchasesPage() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedPurchaseId = searchParams.get('purchaseId');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('');
  const [gateway, setGateway] = useState('');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      kind: kind || undefined,
      gateway: gateway || undefined,
    }),
    [offset, search, status, kind, gateway],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.purchases(filters),
    queryFn: () => fetchPlatformPurchases(filters),
  });

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;

  const openPurchase = (purchaseId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('purchaseId', purchaseId);
    setSearchParams(next);
  };

  const closePurchase = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('purchaseId');
    setSearchParams(next, { replace: true });
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="purchases-page"
    >
      <DocumentTitle title={t('purchases.title')} />

      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            {t('purchases.eyebrow')}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">{t('purchases.title')}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{t('purchases.subtitle')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}>
          <RefreshCw className={cn('size-4', query.isFetching && 'animate-spin')} aria-hidden />
          {t('common.refresh')}
        </Button>
      </section>

      <AdminListFilters
        search={search}
        onSearchChange={(value) => {
          setSearch(value);
          setOffset(0);
        }}
        searchPlaceholderKey="purchases.searchPlaceholder"
        status={status}
        onStatusChange={(value) => {
          setStatus(value);
          setOffset(0);
        }}
        statusOptions={STATUS_OPTIONS.map((value) => ({
          value,
          labelKey: `purchases.status.${value}`,
        }))}
        secondary={kind}
        onSecondaryChange={(value) => {
          setKind(value);
          setOffset(0);
        }}
        secondaryOptions={KIND_OPTIONS.map((value) => ({
          value,
          labelKey: `purchases.kinds.${value}`,
        }))}
        secondaryLabelKey="purchases.kind"
        testIdPrefix="purchases"
      />

      <div className="flex flex-wrap gap-2">
        <label className="text-xs text-muted-foreground flex items-center gap-2">
          {t('purchases.gateway')}
          <select
            className="h-9 rounded-md border border-input bg-transparent px-2 text-sm"
            value={gateway}
            onChange={(e) => {
              setGateway(e.target.value);
              setOffset(0);
            }}
            data-testid="purchases-gateway"
          >
            <option value="">{t('common.all')}</option>
            {GATEWAY_OPTIONS.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Receipt className="size-4" aria-hidden />
            {t('purchases.title')}
            {query.data ? (
              <Badge variant="secondary" appearance="light" size="sm">
                {total.toLocaleString(i18n.language)}
              </Badge>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {query.isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : query.isError ? (
            <p className="p-6 text-sm text-destructive">{getErrorMessage(query.error, t)}</p>
          ) : items.length === 0 ? (
            <div
              className="flex flex-col items-center gap-2 py-16 text-muted-foreground"
              data-testid="purchases-empty"
            >
              <SearchX className="size-8 opacity-60" aria-hidden />
              <p>{t('purchases.empty')}</p>
            </div>
          ) : (
            <div className="overflow-x-auto" data-testid="purchases-list">
              <table className="w-full min-w-[1080px] text-sm">
                <thead className="border-b bg-muted/40 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.detailTitle')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.workspace')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.product')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.kind')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.amount')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.gateway')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('common.status')}</th>
                    <th className="px-4 py-3 text-start font-medium">{t('purchases.created')}</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((purchase) => (
                    <tr
                      key={purchase.id}
                      className="group border-b last:border-0 hover:bg-muted/25"
                      data-testid={`purchase-row-${purchase.id}`}
                    >
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => openPurchase(purchase.id)}
                          className="font-mono text-xs text-primary hover:underline"
                        >
                          {purchase.id.slice(0, 8)}…
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <PurchaseWorkspaceCell workspace={purchase.workspace} />
                      </td>
                      <td className="px-4 py-3">
                        <PurchaseProductCell kind={purchase.kind} target={purchase.target} />
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="outline" appearance="light" size="sm">
                          {purchaseKindLabel(t, purchase.kind)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 font-medium tabular-nums">
                        {formatMoney(purchase.amount, purchase.currency)}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary" appearance="outline" size="sm" className="font-mono">
                          {purchase.gateway_code}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <PurchaseStatusBadge status={purchase.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground tabular-nums">
                        {formatAdminDate(purchase.created_at, i18n.language)}
                      </td>
                      <td className="px-4 py-3 text-end">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openPurchase(purchase.id)}
                        >
                          {t('purchases.viewDetails')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <AdminPagination
        offset={offset}
        limit={PAGE_SIZE}
        total={total}
        onPageChange={setOffset}
        testId="purchases-pagination"
      />

      <Sheet open={Boolean(selectedPurchaseId)} onOpenChange={(open) => !open && closePurchase()}>
        <SheetContent
          side="end"
          className={PURCHASE_DETAIL_PANEL}
          data-testid="purchase-detail-sheet"
        >
          {selectedPurchaseId ? (
            <PurchaseDetailContent purchaseId={selectedPurchaseId} onClose={closePurchase} />
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
