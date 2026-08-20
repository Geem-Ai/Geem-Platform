import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';

type AdminPaginationProps = {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  testId?: string;
};

export function AdminPagination({
  total,
  limit,
  offset,
  onPageChange,
  testId = 'admin-pagination',
}: AdminPaginationProps) {
  const { t, i18n } = useTranslation();
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <nav
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between w-full"
      aria-label={t('common.pagination')}
      data-testid={testId}
    >
      <p className="text-xs text-muted-foreground tabular-nums">
        {t('common.range', {
          from: from.toLocaleString(i18n.language),
          to: to.toLocaleString(i18n.language),
          total: total.toLocaleString(i18n.language),
        })}
      </p>
      <div className="grid w-full grid-cols-2 items-center gap-2 sm:flex sm:w-auto sm:flex-nowrap">
        <Button
          variant="outline"
          size="sm"
          disabled={!hasPrev}
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          data-testid={`${testId}-prev`}
          className="w-full sm:w-auto"
        >
          <ChevronLeft className="size-3.5 rtl:rotate-180" aria-hidden />
          <span>{t('common.previous')}</span>
        </Button>
        <span className="order-first col-span-2 px-1 text-center text-xs tabular-nums whitespace-nowrap text-muted-foreground sm:order-none sm:col-span-1">
          {t('common.page', { page, pages: totalPages })}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasNext}
          onClick={() => onPageChange(offset + limit)}
          data-testid={`${testId}-next`}
          className="w-full sm:w-auto"
        >
          <span>{t('common.next')}</span>
          <ChevronRight className="size-3.5 rtl:rotate-180" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
