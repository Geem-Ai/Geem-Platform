import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { formatCount, formatPeriodDate, formatPeriodDateTime, formatRelativeTime } from '@/features/usage/lib/quota';
import type { ApiUsageHistoryItem, ApiUsagePeriodKey } from '@/services/api/api-keys';
import { PUBLIC_MODEL_ID } from '@/lib/public-model';
import { apiUsageDayBucket, groupApiUsageByDay } from '../lib/history';
import { apiUsageHref } from '../lib/period';
import { maskedApiKey } from '../lib/status';

type ApiUsageHistoryListProps = {
  items: ApiUsageHistoryItem[];
  loading: boolean;
  period: ApiUsagePeriodKey;
  keyFilter: string | null;
  page: number;
  total: number;
  pageSize: number;
};

function HistorySkeleton() {
  return (
    <div className="space-y-0" data-testid="api-usage-history-loading">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-5 py-3.5 border-t first:border-t-0 border-border"
        >
          <div className="size-8 rounded-lg bg-muted animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-3.5 w-40 rounded bg-muted animate-pulse" />
            <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          </div>
          <div className="h-3.5 w-20 rounded bg-muted animate-pulse" />
        </div>
      ))}
    </div>
  );
}

function PaginationButton({
  to,
  disabled,
  children,
}: {
  to: string;
  disabled: boolean;
  children: ReactNode;
}) {
  const contentClass = 'inline-flex flex-row items-center gap-1.5 shrink-0';
  if (disabled) {
    return (
      <Button variant="outline" size="sm" disabled className={contentClass}>
        {children}
      </Button>
    );
  }
  return (
    <Button variant="outline" size="sm" asChild className={contentClass}>
      <Link to={to} className={contentClass}>
        {children}
      </Link>
    </Button>
  );
}

export function ApiUsageHistoryList({
  items,
  loading,
  period,
  keyFilter,
  page,
  total,
  pageSize,
}: ApiUsageHistoryListProps) {
  const { t, i18n } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(safePage * pageSize, total);

  if (loading) return <HistorySkeleton />;

  if (items.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center py-12 px-4 text-center"
        data-testid="api-usage-history-empty"
      >
        <div className="size-11 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-3">
          <Activity className="size-4" aria-hidden />
        </div>
        <p className="text-sm font-medium">{t('apiUsage.noHistoryTitle')}</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-sm leading-relaxed">
          {t('apiUsage.noHistory')}
        </p>
      </div>
    );
  }

  const groups = groupApiUsageByDay(items);

  return (
    <div>
      {groups.map((group) => {
          const first = group.items[0];
          const bucket = first ? apiUsageDayBucket(first.created_at) : 'other';
          const label =
            bucket === 'today'
              ? t('apiUsage.today')
              : bucket === 'yesterday'
                ? t('apiUsage.yesterday')
                : (formatPeriodDate(first?.created_at ?? null, i18n.language) ?? group.key);
          return (
            <section key={group.key} className="border-t border-border first:border-t-0">
              <h2 className="px-5 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground bg-muted/40">
                {label}
              </h2>
              <ul className="divide-y divide-border">
                {group.items.map((item) => (
                  <HistoryRow key={item.id} item={item} />
                ))}
              </ul>
            </section>
          );
        })}

      {total > 0 ? (
        <nav
          className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between w-full px-5 py-4 border-t border-border"
          aria-label={t('apiUsage.recentTitle')}
        >
          <p className="text-xs text-muted-foreground tabular-nums">
            {t('apiUsage.historyRange', {
              from: from.toLocaleString(i18n.language),
              to: to.toLocaleString(i18n.language),
              total: total.toLocaleString(i18n.language),
            })}
          </p>
          {total > pageSize ? (
            <div className="flex flex-nowrap items-center gap-2">
              <PaginationButton
                to={apiUsageHref(period, keyFilter, Math.max(1, safePage - 1))}
                disabled={safePage <= 1}
              >
                <ChevronLeft className="size-3.5 rtl:rotate-180" aria-hidden />
                <span>{t('apiUsage.previous')}</span>
              </PaginationButton>
              <span className="text-xs text-muted-foreground tabular-nums px-1 whitespace-nowrap">
                {t('apiUsage.historyPage', { page: safePage, pages: totalPages })}
              </span>
              <PaginationButton
                to={apiUsageHref(period, keyFilter, Math.min(totalPages, safePage + 1))}
                disabled={safePage >= totalPages}
              >
                <span>{t('apiUsage.next')}</span>
                <ChevronRight className="size-3.5 rtl:rotate-180" aria-hidden />
              </PaginationButton>
            </div>
          ) : null}
        </nav>
      ) : null}
    </div>
  );
}

function HistoryRow({ item }: { item: ApiUsageHistoryItem }) {
  const { t, i18n } = useTranslation();
  const exact = formatPeriodDateTime(item.created_at, i18n.language);
  const time = new Intl.DateTimeFormat(i18n.language, {
    timeStyle: 'short',
  }).format(new Date(item.created_at));
  const familyKey = `apiUsage.family.${item.family}`;
  const familyLabel = t(familyKey, { defaultValue: item.family });

  return (
    <li className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,1fr)_auto_auto] gap-x-4 gap-y-1 px-5 py-3.5 items-start">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium truncate">
            {item.api_key_name || t('apiUsage.unknownKey')}
          </p>
          <Badge variant="secondary" appearance="light" size="sm">
            {familyLabel}
          </Badge>
        </div>
        {item.prefix ? (
          <p className="font-mono text-xs text-muted-foreground" dir="ltr">
            {maskedApiKey({
              prefix: item.prefix,
              last_four: item.last_four ?? '',
            })}
          </p>
        ) : null}
        {item.model ? (
          <p className="font-mono text-[11px] text-muted-foreground/80" dir="ltr">
            {PUBLIC_MODEL_ID}
          </p>
        ) : null}
      </div>
      <div className="hidden sm:flex flex-col items-end justify-center min-h-8">
        <Tooltip>
          <TooltipTrigger asChild>
            <time
              dateTime={item.created_at}
              className="text-xs text-muted-foreground tabular-nums cursor-default"
            >
              {time}
            </time>
          </TooltipTrigger>
          {exact ? (
            <TooltipContent side="bottom" className="font-mono tabular-nums">
              {exact}
            </TooltipContent>
          ) : null}
        </Tooltip>
      </div>
      <div className="text-end shrink-0 min-h-8 flex flex-col items-end justify-center">
        <p className="tabular-nums text-sm font-medium">
          {formatCount(item.billed_tokens, i18n.language)}
        </p>
        <p className="sm:hidden text-[11px] text-muted-foreground mt-0.5">
          {formatRelativeTime(item.created_at, i18n.language)}
        </p>
      </div>
    </li>
  );
}
