/** Display helpers for Platform Admin commerce surfaces (Phase 12C). */

const BYTES_PER_GB = 1024 ** 3;

export function formatMoney(amount: string | null | undefined, currency = 'SAR'): string {
  if (amount == null || amount.trim() === '') return '—';
  const code = (currency || 'SAR').trim().toUpperCase() || 'SAR';
  return `${code} ${amount.trim()}`;
}

export function formatInteger(value: number | null | undefined, locale: string): string {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString(locale);
}

export function formatTokens(value: number | null | undefined, locale: string): string {
  return formatInteger(value, locale);
}

export function bytesToGbInput(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes) || bytes < 0) return '';
  const gb = bytes / BYTES_PER_GB;
  if (Number.isInteger(gb)) return String(gb);
  return gb.toFixed(3).replace(/\.?0+$/, '');
}

export function gbInputToBytes(gbText: string): number | null {
  const trimmed = gbText.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * BYTES_PER_GB);
}

export function entitlementValueAsNumber(value: number | boolean | string | null | undefined): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'string') {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  }
  return 0;
}
