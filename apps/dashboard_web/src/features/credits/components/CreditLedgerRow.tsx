import { ArrowDownRight, ArrowUpDown, ArrowUpRight, Clock3, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import {
  creditEntryTypeKey,
  creditLedgerDelta,
  formatSignedCredits,
} from '@/features/credits/lib/ledger';
import { formatAdminDateTime } from '@/lib/dates';
import { formatInteger } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PlatformCreditLedgerItem } from '@/services/api/types';

type CreditLedgerRowProps = {
  entry: PlatformCreditLedgerItem;
  locale: string;
  tableBreakpoint?: 'xl' | '2xl';
};

export function CreditLedgerRow({
  entry,
  locale,
  tableBreakpoint = '2xl',
}: CreditLedgerRowProps) {
  const { t } = useTranslation();
  const spec = ledgerTypeSpec(entry.entry_type);
  const delta = creditLedgerDelta(entry);
  const TypeIcon = spec.icon;
  const rowGrid =
    tableBreakpoint === 'xl'
      ? 'xl:grid-cols-[minmax(100px,0.6fr)_minmax(180px,1.35fr)_minmax(95px,0.7fr)_minmax(80px,0.55fr)_minmax(115px,0.8fr)] xl:items-center'
      : '2xl:grid-cols-[minmax(100px,0.6fr)_minmax(180px,1.35fr)_minmax(95px,0.7fr)_minmax(80px,0.55fr)_minmax(115px,0.8fr)] 2xl:items-center';
  const mobileLabel = tableBreakpoint === 'xl' ? 'xl:sr-only' : '2xl:sr-only';

  return (
    <li
      className={cn('grid gap-4 p-4', rowGrid)}
      data-testid="credits-history-row"
    >
      <div>
        <Badge variant={spec.variant} appearance="light" size="sm">
          <TypeIcon className="size-3" aria-hidden />
          {t(spec.labelKey)}
        </Badge>
      </div>

      <div className="min-w-0">
        <p
          className="break-words text-sm leading-5 text-foreground"
          title={entry.reason || undefined}
        >
          {entry.reason || t('credits.noReason')}
        </p>
        {entry.request_id ? (
          <p
            className="mt-1 truncate font-mono text-[10px] text-muted-foreground"
            title={entry.request_id}
          >
            <bdi dir="ltr">{entry.request_id}</bdi>
          </p>
        ) : null}
        {entry.remaining_amount != null ? (
          <p className="mt-1 text-[11px] text-muted-foreground">
            {t('credits.remainingInline', {
              count: formatInteger(entry.remaining_amount, locale),
            })}
          </p>
        ) : null}
      </div>

      <div className="min-w-0 text-xs text-muted-foreground">
        <span className={mobileLabel}>{t('credits.columns.source')}: </span>
        {entry.source_type ? (
          <bdi dir="ltr" className="break-all" title={entry.source_type}>
            {entry.source_type}
          </bdi>
        ) : (
          t('common.none')
        )}
      </div>

      <div
        className={cn(
          'text-sm font-semibold tabular-nums',
          delta < 0
            ? 'text-amber-700 dark:text-amber-300'
            : 'text-green-700 dark:text-green-300',
        )}
        data-testid="credits-entry-amount"
      >
        <span className={cn('font-normal text-muted-foreground', mobileLabel)}>
          {t('credits.columns.change')}: {' '}
        </span>
        <bdi dir="ltr">{formatSignedCredits(delta, locale)}</bdi>
      </div>

      <div className="text-xs text-muted-foreground">
        <span className={mobileLabel}>{t('credits.columns.occurred')}: </span>
        <span className="tabular-nums">{formatAdminDateTime(entry.created_at, locale)}</span>
      </div>
    </li>
  );
}

function ledgerTypeSpec(entryType: string): {
  labelKey: string;
  variant: 'success' | 'warning' | 'info' | 'secondary';
  icon: LucideIcon;
} {
  switch (creditEntryTypeKey(entryType)) {
    case 'grant':
      return { labelKey: 'credits.entryTypes.grant', variant: 'success', icon: ArrowUpRight };
    case 'consume':
      return { labelKey: 'credits.entryTypes.consume', variant: 'warning', icon: ArrowDownRight };
    case 'expire':
      return { labelKey: 'credits.entryTypes.expire', variant: 'warning', icon: Clock3 };
    case 'adjust':
      return { labelKey: 'credits.entryTypes.adjust', variant: 'info', icon: ArrowUpDown };
    default:
      return { labelKey: 'credits.entryTypes.unknown', variant: 'secondary', icon: ArrowUpDown };
  }
}
