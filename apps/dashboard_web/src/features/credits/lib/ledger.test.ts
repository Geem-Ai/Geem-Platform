import { describe, expect, it } from 'vitest';
import {
  creditEntryTypeKey,
  creditLedgerDelta,
  formatSignedCredits,
} from './ledger';

describe('credit ledger display helpers', () => {
  it('derives signed balance movement from non-negative ledger magnitudes', () => {
    expect(creditLedgerDelta({ entry_type: 'grant', amount: 500 })).toBe(500);
    expect(creditLedgerDelta({ entry_type: 'adjust', amount: 25 })).toBe(25);
    expect(creditLedgerDelta({ entry_type: 'consume', amount: 75 })).toBe(-75);
    expect(creditLedgerDelta({ entry_type: 'expire', amount: 10 })).toBe(-10);
  });

  it('formats semantic signs and normalizes unknown entry labels', () => {
    expect(formatSignedCredits(1250, 'en-US')).toBe('+1,250');
    expect(formatSignedCredits(-1250, 'en-US')).toBe('−1,250');
    expect(creditEntryTypeKey('future_kind')).toBe('unknown');
  });
});
