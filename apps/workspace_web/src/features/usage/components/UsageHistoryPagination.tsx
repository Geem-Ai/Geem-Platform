import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  historyPageHref,
  type HistoryDateRange,
  type HistoryKindFilter,
} from '../lib/history';

type UsageHistoryPaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  kind?: HistoryKindFilter;
  dates?: HistoryDateRange;
};

function PaginationButton({
  to,
  disabled,
  testId,
  children,
}: {
  to: string;
  disabled: boolean;
  testId: string;
  children: ReactNode;
}) {
  const contentClass = 'inline-flex flex-row items-center gap-1.5 shrink-0';

  if (disabled) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        data-testid={testId}
        className={contentClass}
      >
        {children}
      </Button>
    );
  }

  return (
    <Button variant="outline" size="sm" asChild className={contentClass}>
      <Link to={to} data-testid={testId} className={contentClass}>
        {children}
      </Link>
    </Button>
  );
}

export function UsageHistoryPagination({
  page,
  pageSize,
  total,
  kind = 'all',
  dates = {},
}: UsageHistoryPaginationProps) {
  const { t, i18n } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(safePage * pageSize, total);
  const hasPrev = safePage > 1;
  const hasNext = safePage < totalPages;

  return (
    <nav
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between w-full"
      aria-label={t('usage.history')}
      data-testid="usage-history-pagination"
    >
      <p className="text-xs text-muted-foreground tabular-nums">
        {t('usage.historyRange', {
          from: from.toLocaleString(i18n.language),
          to: to.toLocaleString(i18n.language),
          total: total.toLocaleString(i18n.language),
        })}
      </p>
      <div className="flex flex-nowrap items-center gap-2">
        <PaginationButton
          to={historyPageHref(safePage - 1, kind, dates)}
          disabled={!hasPrev}
          testId="usage-history-prev"
        >
          <ChevronLeft className="size-3.5 rtl:rotate-180" aria-hidden />
          <span>{t('usage.historyPrevious')}</span>
        </PaginationButton>
        <span
          className="text-xs text-muted-foreground tabular-nums px-1 whitespace-nowrap"
          data-testid="usage-history-page-label"
        >
          {t('usage.historyPage', { page: safePage, pages: totalPages })}
        </span>
        <PaginationButton
          to={historyPageHref(safePage + 1, kind, dates)}
          disabled={!hasNext}
          testId="usage-history-next"
        >
          <span>{t('usage.historyNext')}</span>
          <ChevronRight className="size-3.5 rtl:rotate-180" aria-hidden />
        </PaginationButton>
      </div>
    </nav>
  );
}
