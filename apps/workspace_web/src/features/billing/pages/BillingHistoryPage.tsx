import { Link, useSearchParams } from 'react-router-dom';
import { CreditCard } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
} from '@/components/ui/card';
import { BILLING_HISTORY_PAGE_SIZE } from '@/services/api/billing';
import { formatPeriodDateTime } from '@/features/usage/lib/quota';
import { BillingPageHeader } from '../components/BillingPageHeader';
import { PurchaseStatusBadge } from '../components/PurchaseStatusBadge';
import { usePurchases } from '../hooks/useBillingQueries';
import {
  historyPageHref,
  parsePurchaseKind,
  parsePurchaseStatus,
  statusQueryValue,
  type PurchaseKindFilter,
  type PurchaseStatusFilter,
} from '../lib/history';
import { formatMoney } from '../lib/money';
import { purchaseKindLabelKey } from '../lib/status';

function parsePage(raw: string | null): number {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.floor(n);
}

function HistorySkeleton() {
  return (
    <div className="space-y-0" data-testid="billing-history-loading">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-5 py-3.5 border-t first:border-t-0 border-border"
        >
          <div className="size-8 rounded-lg bg-muted animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-40 rounded bg-muted animate-pulse" />
            <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

const KIND_FILTERS: PurchaseKindFilter[] = ['all', 'subscription', 'credit_pack'];
const STATUS_FILTERS: PurchaseStatusFilter[] = [
  'all',
  'paid',
  'pending',
  'failed',
  'cancelled',
  'expired',
];

export function BillingHistoryPage() {
  const { t, i18n } = useTranslation();
  const [params] = useSearchParams();
  const page = parsePage(params.get('page'));
  const kind = parsePurchaseKind(params.get('kind'));
  const status = parsePurchaseStatus(params.get('status'));
  const offset = (page - 1) * BILLING_HISTORY_PAGE_SIZE;
  const query = usePurchases({
    limit: BILLING_HISTORY_PAGE_SIZE,
    offset,
    kind: kind === 'all' ? undefined : kind,
    status: statusQueryValue(status),
  });

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / BILLING_HISTORY_PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const from = total === 0 ? 0 : (safePage - 1) * BILLING_HISTORY_PAGE_SIZE + 1;
  const to = Math.min(safePage * BILLING_HISTORY_PAGE_SIZE, total);

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-8 ms-auto me-auto">
      <DocumentTitle title={t('billing.historyTitle')} />
      <BillingPageHeader
        eyebrow={t('billing.eyebrow')}
        title={t('billing.historyTitle')}
        description={t('billing.historyDescription')}
        onRefresh={() => void query.refetch()}
        refreshing={query.isFetching}
      />

      <Card className="shadow-xs">
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('billing.purchases')}</CardTitle>
            <CardDescription>{t('billing.purchasesHint')}</CardDescription>
          </CardHeading>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1.5" data-testid="billing-history-kind-filters">
              {KIND_FILTERS.map((value) => (
                <Button
                  key={value}
                  variant={kind === value ? 'primary' : 'outline'}
                  size="sm"
                  asChild
                >
                  <Link to={historyPageHref(1, value, status)}>
                    {t(`billing.filterKind.${value}`)}
                  </Link>
                </Button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5" data-testid="billing-history-status-filters">
              {STATUS_FILTERS.map((value) => (
                <Button
                  key={value}
                  variant={status === value ? 'primary' : 'outline'}
                  size="sm"
                  asChild
                >
                  <Link to={historyPageHref(1, kind, value)}>
                    {t(`billing.filterStatus.${value}`)}
                  </Link>
                </Button>
              ))}
            </div>
          </div>

          {query.isLoading ? <HistorySkeleton /> : null}

          {query.isError && !query.isLoading ? (
            <div data-testid="billing-history-error" className="space-y-3 py-6 text-center">
              <p className="text-sm text-destructive">{t('billing.loadError')}</p>
              <Button type="button" onClick={() => void query.refetch()}>
                {t('billing.retry')}
              </Button>
            </div>
          ) : null}

          {!query.isLoading && !query.isError && items.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center py-12 px-4 text-center"
              data-testid="billing-history-empty"
            >
              <div className="size-11 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-3">
                <CreditCard className="size-4" aria-hidden />
              </div>
              <p className="text-sm font-medium">{t('billing.historyEmpty')}</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm leading-relaxed">
                {t('billing.historyEmptyHint')}
              </p>
              <div className="flex flex-wrap gap-2 mt-4">
                <Button asChild size="sm">
                  <Link to="/billing/subscription">{t('billing.viewPlans')}</Link>
                </Button>
                <Button asChild size="sm" variant="outline">
                  <Link to="/billing/credits">{t('billing.buyCredits')}</Link>
                </Button>
              </div>
            </div>
          ) : null}

          {!query.isLoading && !query.isError && items.length > 0 ? (
            <ul className="divide-y divide-border" data-testid="billing-history-list">
              {items.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-col gap-2 py-3.5 sm:flex-row sm:items-center sm:justify-between"
                  data-testid="billing-history-row"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium truncate">
                        {item.item_name || t(purchaseKindLabelKey(item.kind))}
                      </p>
                      <PurchaseStatusBadge status={item.status} />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t(purchaseKindLabelKey(item.kind))}
                      {' · '}
                      {formatPeriodDateTime(item.created_at, i18n.language)}
                    </p>
                    <p className="text-[11px] font-mono text-muted-foreground truncate">
                      {item.id}
                    </p>
                  </div>
                  <p className="text-sm font-semibold tabular-nums shrink-0">
                    {formatMoney(item.amount, item.currency)}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}

          {total > 0 ? (
            <nav
              className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
              aria-label={t('billing.historyTitle')}
            >
              <p className="text-xs text-muted-foreground tabular-nums">
                {t('usage.historyRange', {
                  from: from.toLocaleString(i18n.language),
                  to: to.toLocaleString(i18n.language),
                  total: total.toLocaleString(i18n.language),
                })}
              </p>
              <div className="flex items-center gap-2">
                {safePage > 1 ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link to={historyPageHref(safePage - 1, kind, status)}>
                      {t('usage.historyPrevious')}
                    </Link>
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" disabled>
                    {t('usage.historyPrevious')}
                  </Button>
                )}
                {safePage < totalPages ? (
                  <Button variant="outline" size="sm" asChild>
                    <Link to={historyPageHref(safePage + 1, kind, status)}>
                      {t('usage.historyNext')}
                    </Link>
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" disabled>
                    {t('usage.historyNext')}
                  </Button>
                )}
              </div>
            </nav>
          ) : null}
        </CardContent>
      </Card>

      <Card className="shadow-xs">
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('billing.creditActivity')}</CardTitle>
            <CardDescription>{t('billing.creditActivityHint')}</CardDescription>
          </CardHeading>
        </CardHeader>
        <CardContent>
          <Button variant="outline" size="sm" asChild>
            <Link
              to="/billing/usage/history?kind=credits"
              data-testid="billing-credit-activity-link"
            >
              {t('billing.viewCreditActivity')}
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}