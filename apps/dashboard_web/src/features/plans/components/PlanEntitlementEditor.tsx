import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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

  return (
    <div className="space-y-3" data-testid={testIdPrefix}>
      {catalog.map((item) => {
        const isStorage = item.key === 'storage_bytes';
        const label = t(`entitlements.${item.key}`, { defaultValue: item.key });
        const unitHint = isStorage
          ? t('entitlements.storageInputHint')
          : t(`entitlements.units.${item.unit}`, { defaultValue: item.unit });
        return (
          <div key={item.key} className="space-y-1.5">
            <Label htmlFor={`${testIdPrefix}-${item.key}`} className="text-sm">
              {label}
              <span className="ms-2 text-xs font-normal text-muted-foreground">{unitHint}</span>
            </Label>
            <Input
              id={`${testIdPrefix}-${item.key}`}
              type="number"
              min={0}
              step={isStorage ? 'any' : 1}
              value={values[item.key] ?? ''}
              disabled={disabled}
              onChange={(e) => onChange({ ...values, [item.key]: e.target.value })}
              data-testid={`${testIdPrefix}-${item.key}`}
            />
          </div>
        );
      })}
    </div>
  );
}
