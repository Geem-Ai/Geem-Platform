/** Format a server-provided money amount. Never compute totals on the client. */
export function formatMoney(amount: string, currency: string): string {
  const code = (currency || 'SAR').trim().toUpperCase() || 'SAR';
  const value = amount.trim() || '0.00';
  return `${code} ${value}`;
}

/** Display-only ordering. Does not calculate payable totals. */
export function compareMoneyAmount(a: string, b: string): number {
  return a.localeCompare(b, 'en', { numeric: true });
}
