import {
  Clock3,
  Coins,
  MinusCircle,
  PlusCircle,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { UsageHistoryItem } from '@/services/api/usage';
import { isAiHistoryKind } from '@/services/api/usage';
import {
  creditDeltaSign,
  groupHistoryByDay,
  historyDayBucket,
  historyKindLabelKey,
  operationLabelKey,
  shortenId,
  sourceLabelKey,
} from '../lib/history';
import {
  formatCount,
  formatPeriodDate,
  formatPeriodDateTime,
  formatRelativeTime,
} from '../lib/quota';

function kindIcon(kind: string) {
  if (kind === 'credit_grant') return PlusCircle;
  if (kind === 'credit_consume') return MinusCircle;
  if (kind === 'credit_adjust') return SlidersHorizontal;
  if (kind === 'credit_expire') return Clock3;
  return Sparkles;
}

function HistoryEmpty({ hint }: { hint: string }) {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-col items-center justify-center py-12 px-4 text-center"
      data-testid="usage-history-empty"
    >
      <div className="size-11 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-3">
        <Coins className="size-4" aria-hidden />
      </div>
      <p className="text-sm font-medium">{t('usage.historyEmpty')}</p>
      <p className="text-xs text-muted-foreground mt-1 max-w-sm leading-relaxed">
        {hint}
      </p>
    </div>
  );
}

function EventIcon({ kind }: { kind: string }) {
  const Icon = kindIcon(kind);
  return (
    <div
      className={cn(
        'size-8 rounded-lg flex items-center justify-center shrink-0',
        isAiHistoryKind(kind)
          ? 'bg-primary/10 text-primary'
          : kind === 'credit_grant'
            ? 'bg-[var(--color-success-soft,var(--color-green-100))] text-[var(--color-success-accent,var(--color-green-700))]'
            : kind === 'credit_consume' || kind === 'credit_expire'
              ? 'bg-muted text-muted-foreground'
              : 'bg-muted text-muted-foreground',
      )}
    >
      <Icon className="size-3.5" aria-hidden />
    </div>
  );
}

function Amount({ item }: { item: UsageHistoryItem }) {
  const { t, i18n } = useTranslation();
  if (item.tokens != null) {
    return (
      <p className="tabular-nums text-sm font-medium">
        {t('usage.historyTokens', {
          count: formatCount(item.tokens, i18n.language),
        })}
      </p>
    );
  }
  if (item.credits != null) {
    const sign = creditDeltaSign(item.kind);
    const count = formatCount(item.credits, i18n.language);
    return (
      <p
        className={cn(
          'tabular-nums text-sm font-medium',
          sign < 0 ? 'text-muted-foreground' : 'text-[var(--color-success-accent,var(--color-green-700))]',
        )}
      >
        {t(sign < 0 ? 'usage.historyCreditsOut' : 'usage.historyCreditsIn', {
          count,
        })}
      </p>
    );
  }
  return null;
}

function EventSubtitle({
  item,
  asTitle = false,
}: {
  item: UsageHistoryItem;
  asTitle?: boolean;
}) {
  const { t } = useTranslation();
  const parts: string[] = [];
  if (isAiHistoryKind(item.kind)) {
    if (item.operation_type) {
      const key = operationLabelKey(item.operation_type);
      parts.push(
        t(key, { defaultValue: item.operation_type.replaceAll('_', ' ') }),
      );
    }
  } else if (item.source_type) {
    const key = sourceLabelKey(item.source_type);
    parts.push(
      t(key, { defaultValue: item.source_type.replaceAll('_', ' ') }),
    );
  }
  if (parts.length === 0) return null;
  return (
    <p
      className={cn(
        'truncate',
        asTitle
          ? 'text-sm font-medium leading-5'
          : 'text-xs text-muted-foreground mt-1',
      )}
    >
      {parts.join(' · ')}
    </p>
  );
}

function TokenSplit({ item }: { item: UsageHistoryItem }) {
  const { t, i18n } = useTranslation();
  if (
    !isAiHistoryKind(item.kind) ||
    (item.input_tokens == null && item.output_tokens == null)
  ) {
    return null;
  }
  return (
    <p className="text-[11px] text-muted-foreground tabular-nums mt-0.5">
      {t('usage.historyTokenSplit', {
        input: formatCount(item.input_tokens ?? 0, i18n.language),
        output: formatCount(item.output_tokens ?? 0, i18n.language),
      })}
    </p>
  );
}

function CompactRow({ item }: { item: UsageHistoryItem }) {
  const { t, i18n } = useTranslation();
  const exact = formatPeriodDateTime(item.created_at, i18n.language);
  return (
    <li
      className="flex items-center justify-between gap-3 py-3.5 first:pt-0 last:pb-0"
      data-testid="usage-history-item"
      data-kind={item.kind}
    >
      <div className="flex items-start gap-3 min-w-0">
        <EventIcon kind={item.kind} />
        <div className="min-w-0">
          <p className="text-sm font-medium leading-none">
            {t(historyKindLabelKey(item.kind))}
          </p>
          <Tooltip>
            <TooltipTrigger asChild>
              <time
                dateTime={item.created_at}
                className="text-xs text-muted-foreground mt-1.5 block cursor-default"
              >
                {formatRelativeTime(item.created_at, i18n.language)}
              </time>
            </TooltipTrigger>
            {exact ? (
              <TooltipContent side="bottom" className="font-mono tabular-nums">
                {exact}
              </TooltipContent>
            ) : null}
          </Tooltip>
        </div>
      </div>
      <div className="text-end shrink-0">
        <Amount item={item} />
      </div>
    </li>
  );
}

function LedgerRow({
  item,
  hideKindTitle,
}: {
  item: UsageHistoryItem;
  hideKindTitle: boolean;
}) {
  const { t, i18n } = useTranslation();
  const exact = formatPeriodDateTime(item.created_at, i18n.language);
  const time = new Intl.DateTimeFormat(i18n.language, {
    timeStyle: 'short',
  }).format(new Date(item.created_at));
  const idLabel = shortenId(item.request_id || item.id);

  return (
    <li
      className="grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,1fr)_minmax(7rem,auto)_auto] gap-x-4 gap-y-1 px-5 py-3.5 items-start"
      data-testid="usage-history-item"
      data-kind={item.kind}
    >
      <div className="flex items-start gap-3 min-w-0">
        <EventIcon kind={item.kind} />
        <div className="min-w-0">
          {hideKindTitle ? (
            <EventSubtitle item={item} asTitle />
          ) : (
            <>
              <p className="text-sm font-medium leading-5">
                {t(historyKindLabelKey(item.kind))}
              </p>
              <EventSubtitle item={item} />
            </>
          )}
          <TokenSplit item={item} />
        </div>
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
        <p className="text-[11px] text-muted-foreground/80 font-mono mt-0.5" title={item.id}>
          {idLabel}
        </p>
      </div>
      <div className="text-end shrink-0 min-h-8 flex flex-col items-end justify-center">
        <Amount item={item} />
        <p className="sm:hidden text-[11px] text-muted-foreground mt-0.5">
          {formatRelativeTime(item.created_at, i18n.language)}
        </p>
      </div>
    </li>
  );
}

type UsageHistoryListProps = {
  items: UsageHistoryItem[];
  variant?: 'compact' | 'ledger';
  emptyHint?: string;
  hideKindTitle?: boolean;
};

export function UsageHistoryList({
  items,
  variant = 'compact',
  emptyHint,
  hideKindTitle = false,
}: UsageHistoryListProps) {
  const { t, i18n } = useTranslation();

  if (items.length === 0) {
    return <HistoryEmpty hint={emptyHint ?? t('usage.historyEmptyHint')} />;
  }

  if (variant === 'compact') {
    return (
      <ul className="divide-y divide-border" data-testid="usage-history-list">
        {items.map((item) => (
          <CompactRow key={item.id} item={item} />
        ))}
      </ul>
    );
  }

  const groups = groupHistoryByDay(items);

  return (
    <div data-testid="usage-history-list">
      {groups.map((group) => {
        const first = group.items[0];
        const bucket = first ? historyDayBucket(first.created_at) : 'other';
        const label =
          bucket === 'today'
            ? t('usage.historyToday')
            : bucket === 'yesterday'
              ? t('usage.historyYesterday')
              : (formatPeriodDate(first?.created_at ?? null, i18n.language) ??
                group.key);
        return (
          <section key={group.key} className="border-t border-border first:border-t-0">
            <h2 className="px-5 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground bg-muted/40">
              {label}
            </h2>
            <ul className="divide-y divide-border">
              {group.items.map((item) => (
                <LedgerRow
                  key={item.id}
                  item={item}
                  hideKindTitle={hideKindTitle}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
