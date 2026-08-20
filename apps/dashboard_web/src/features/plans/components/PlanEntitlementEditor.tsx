import { useTranslation } from 'react-i18next';
import { Gauge, HardDrive, Sparkles, UsersRound, type LucideIcon } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { bytesToGbInput, entitlementValueAsNumber, gbInputToBytes } from '@/lib/format';
import type { PlatformEntitlementCatalogItem } from '@/services/api/types';

export type EntitlementDraft = Record<string, string>;

type PlanEntitlementEditorProps = {
  catalog: PlatformEntitlementCatalogItem[];
  values: EntitlementDraft;
  onChange: (next: EntitlementDraft) => void;
  disabled?: boolean;
  testIdPrefix?: string;
};

export function entitlementDraftFromItems(
  catalog: PlatformEntitlementCatalogItem[],
  items: { key: string; value: number | boolean | string }[] = [],
): EntitlementDraft {
  const map = new Map(items.map((i) => [i.key, i.value]));
  const draft: EntitlementDraft = {};
  for (const item of catalog) {
    const raw = map.get(item.key);
    if (item.key === 'storage_bytes') {
      draft[item.key] = raw != null ? bytesToGbInput(entitlementValueAsNumber(raw)) : '';
    } else {
      draft[item.key] = raw != null ? String(entitlementValueAsNumber(raw)) : '';
    }
  }
  return draft;
}

export function entitlementDraftToPayload(
  catalog: PlatformEntitlementCatalogItem[],
  draft: EntitlementDraft,
): { key: string; value: number }[] | { errorKey: string } {
  const out: { key: string; value: number }[] = [];
  for (const item of catalog) {
    const text = (draft[item.key] ?? '').trim();
    if (!text) {
      return { errorKey: 'plans.entitlementRequired' };
    }
    if (item.key === 'storage_bytes') {
      const bytes = gbInputToBytes(text);
      if (bytes == null || !Number.isInteger(bytes) || bytes < 0) {
        return { errorKey: 'plans.storageInvalid' };
      }
      out.push({ key: item.key, value: bytes });
      continue;
    }
    const n = Number(text);
    if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0) {
      return { errorKey: 'plans.entitlementInvalidValue' };
    }
    out.push({ key: item.key, value: n });
  }
  return out;
}

export function PlanEntitlementEditor({
  catalog,
  values,
  onChange,
  disabled,
  testIdPrefix = 'plan-entitlements',
}: PlanEntitlementEditorProps) {
  const { t } = useTranslation();

  if (catalog.length === 0) {
    return (
      <div
        className="flex min-h-28 items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-5 py-8 text-center text-sm text-muted-foreground"
        data-testid={testIdPrefix}
      >
        {t('plans.noEntitlements')}
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2" data-testid={testIdPrefix}>
      {catalog.map((item) => {
        const isStorage = item.key === 'storage_bytes';
        const label = t(`entitlements.${item.key}`, { defaultValue: item.key });
        const unitHint = isStorage
          ? t('entitlements.storageInputHint')
          : t(`entitlements.units.${item.unit}`, { defaultValue: item.unit });
        const Icon = entitlementIcon(item.key);
        const hintId = `${testIdPrefix}-${item.key}-hint`;
        return (
          <div
            key={item.key}
            className={cn(
              'rounded-xl border border-border bg-muted/15 p-4 transition-colors',
              'focus-within:border-primary/40 focus-within:bg-primary/[0.025] focus-within:ring-3 focus-within:ring-primary/8',
              disabled && 'opacity-65',
            )}
          >
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 grow">
                <Label
                  htmlFor={`${testIdPrefix}-${item.key}`}
                  className="block truncate text-sm font-medium"
                >
                  {label}
                </Label>
                <p id={hintId} className="mt-0.5 truncate text-xs text-muted-foreground">
                  {unitHint}
                </p>
              </div>
            </div>
            <Input
              id={`${testIdPrefix}-${item.key}`}
              name={item.key}
              type="number"
              inputMode={isStorage ? 'decimal' : 'numeric'}
              min={0}
              step={isStorage ? 'any' : 1}
              required
              dir="ltr"
              aria-describedby={hintId}
              value={values[item.key] ?? ''}
              disabled={disabled}
              onChange={(e) => onChange({ ...values, [item.key]: e.target.value })}
              className="mt-4 bg-background font-mono tabular-nums"
              data-testid={`${testIdPrefix}-${item.key}`}
            />
          </div>
        );
      })}
    </div>
  );
}

function entitlementIcon(key: string): LucideIcon {
  if (key === 'storage_bytes') return HardDrive;
  if (key === 'experts_limit') return UsersRound;
  if (key.startsWith('ai_tokens_')) return Sparkles;
  return Gauge;
}
