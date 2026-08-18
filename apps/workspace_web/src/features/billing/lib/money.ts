export function normalizeMoneyCurrency(currency: string): string {
  return (currency || 'SAR').trim().toUpperCase() || 'SAR';
}

export function normalizeMoneyValue(amount: string): string {
  return amount.trim() || '0.00';
}

/**
 * Plain-text money label for aria / tests / non-React contexts.
 * UI should render {@link MoneyAmount} so SAR uses the official symbol SVG.
 */
export function formatMoney(amount: string, currency: string): string {
  const code = normalizeMoneyCurrency(currency);
  const value = normalizeMoneyValue(amount);
  return `${code} ${value}`;
}

/** Display-only ordering. Does not calculate payable totals. */
export function compareMoneyAmount(a: string, b: string): number {
  return a.localeCompare(b, 'en', { numeric: true });
}
