import type { TFunction } from 'i18next';

export function purchaseStatusLabel(t: TFunction, status: string): string {
  const key = `purchases.status.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}

export function purchaseKindLabel(t: TFunction, kind: string): string {
  const key = `purchases.kinds.${kind}`;
  const translated = t(key);
  return translated === key ? kind : translated;
}
