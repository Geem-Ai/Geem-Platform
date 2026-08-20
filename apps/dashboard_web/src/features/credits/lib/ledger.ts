import { formatInteger } from '@/lib/format';
import type { PlatformCreditLedgerItem } from '@/services/api/types';

const DEBIT_ENTRY_TYPES = new Set(['consume', 'expire', 'reserve']);

export function creditLedgerDelta(
  entry: Pick<PlatformCreditLedgerItem, 'entry_type' | 'amount'>,
): number {
  const magnitude = Math.abs(entry.amount);
  return DEBIT_ENTRY_TYPES.has(entry.entry_type) ? -magnitude : magnitude;
}

export function formatSignedCredits(value: number, locale: string): string {
  const sign = value < 0 ? '−' : '+';
  return `${sign}${formatInteger(Math.abs(value), locale)}`;
}

export function creditEntryTypeKey(
  entryType: string,
): 'grant' | 'consume' | 'adjust' | 'expire' | 'unknown' {
  if (
    entryType === 'grant' ||
    entryType === 'consume' ||
    entryType === 'adjust' ||
    entryType === 'expire'
  ) {
    return entryType;
  }
  return 'unknown';
}
