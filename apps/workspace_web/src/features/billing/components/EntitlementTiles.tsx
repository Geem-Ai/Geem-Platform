import type { LucideIcon } from 'lucide-react';
import { CalendarDays, HardDrive, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { BillingEntitlement } from '@/services/api/billing';
import type { EntitlementItem } from '@/services/api/usage';
import type { ByteUnitKey } from '@/features/usage/lib/quota';
import {
  entitlementLabelKey,
  formatEntitlementValue,
  isEntitlementI18nValue,
  sortEntitlements,
} from '../lib/entitlements';

function entitlementIcon(key: string): LucideIcon {
  if (key === 'storage_bytes') return HardDrive;
  if (key === 'experts_limit') return Sparkles;
  return CalendarDays;
}

export function EntitlementTiles({
  items,
  testId,
}: {
  items: readonly (BillingEntitlement | EntitlementItem)[];
  testId?: string;
}) {
  const { t, i18n } = useTranslation();
  const byteUnit = (unit: ByteUnitKey) => t(`usage.units.${unit}`);
  const ordered = sortEntitlements(items);

  return (
    <ul
      className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
      data-testid={testId}
    >
      {ordered.map((item) => {
        const Icon = entitlementIcon(item.key);
        const formatted = formatEntitlementValue(item, i18n.language, byteUnit);
        const value = isEntitlementI18nValue(formatted) ? t(formatted) : formatted;
        return (
          <li
            key={item.key}
            data-entitlement-key={item.key}
            className="rounded-xl border border-border bg-muted/40 px-3 py-3"
          >
            <div className="flex items-center gap-2 text-muted-foreground mb-1.5">
              <div className="size-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                <Icon className="size-3.5" aria-hidden />
              </div>
              <p className="text-[11px] font-medium leading-4">
                {t(entitlementLabelKey(item.key), { key: item.key })}
              </p>
            </div>
            <p className="text-sm font-semibold tabular-nums tracking-tight">{value}</p>
          </li>
        );
      })}
    </ul>
  );
}
