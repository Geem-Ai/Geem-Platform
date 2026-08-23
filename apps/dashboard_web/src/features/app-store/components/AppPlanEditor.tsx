import { useTranslation } from 'react-i18next';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { entitlementValueAsNumber } from '@/lib/format';
import type {
  PlatformAppEntitlementCatalogItem,
  PlatformAppPlanEntitlement,
  PlatformAppPlanEntitlementInput,
} from '@/services/api/types';

export type AppPlanDraft = {
  code: string;
  name: string;
  description: string;
  priceAmount: string;
  billingInterval: string;
  isDefault: boolean;
  entitlements: Record<string, string>;
};

export function emptyAppPlanDraft(billingType: string): AppPlanDraft {
  return normalizePlanDraftForBilling(
    {
      code: '',
      name: '',
      description: '',
      priceAmount: '',
      billingInterval: 'none',
      isDefault: false,
      entitlements: {},
    },
    billingType,
  );
}

export function normalizePlanDraftForBilling(
  draft: AppPlanDraft,
  billingType: string,
): AppPlanDraft {
  if (billingType === 'free') {
    return { ...draft, priceAmount: '0.00', billingInterval: 'none' };
  }
  if (billingType === 'one_time') {
    return { ...draft, billingInterval: 'none' };
  }
  if (billingType === 'subscription' && draft.billingInterval === 'none') {
    return { ...draft, billingInterval: 'monthly' };
  }
  return draft;
}

export function appPlanDraftFromPlan(
  plan: {
    code: string;
    name: string;
    description?: string | null;
    price_amount: string;
    billing_interval: string;
    is_default: boolean;
    entitlements: PlatformAppPlanEntitlement[];
  },
  catalog: PlatformAppEntitlementCatalogItem[],
  billingType: string,
): AppPlanDraft {
  const entMap = new Map(plan.entitlements.map((e) => [e.key, e.value]));
  const entitlements: Record<string, string> = {};
  for (const item of catalog) {
    const raw = entMap.get(item.key);
    entitlements[item.key] = raw != null ? String(entitlementValueAsNumber(raw)) : '';
  }
  return normalizePlanDraftForBilling(
    {
      code: plan.code,
      name: plan.name,
      description: plan.description ?? '',
      priceAmount: plan.price_amount,
      billingInterval: plan.billing_interval,
      isDefault: plan.is_default,
      entitlements,
    },
    billingType,
  );
}

export function appPlanDraftToCreateBody(
  draft: AppPlanDraft,
  catalog: PlatformAppEntitlementCatalogItem[],
): PlatformAppPlanEntitlementInput[] | { errorKey: string } {
  if (!draft.code.trim() || !draft.name.trim()) {
    return { errorKey: 'appStore.planFieldsRequired' };
  }
  const entitlements: PlatformAppPlanEntitlementInput[] = [];
  for (const item of catalog) {
    const text = (draft.entitlements[item.key] ?? '').trim();
    if (!text) continue;
    const n = Number(text);
    if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0) {
      return { errorKey: 'appStore.entitlementInvalidValue' };
    }
    entitlements.push({ key: item.key, value: n });
  }
  return entitlements;
}

type AppPlanEditorProps = {
  draft: AppPlanDraft;
  onChange: (next: AppPlanDraft) => void;
  catalog: PlatformAppEntitlementCatalogItem[];
  billingType: string;
  codeLocked?: boolean;
  disabled?: boolean;
  testIdPrefix?: string;
};

export function AppPlanEditor({
  draft,
  onChange,
  catalog,
  billingType,
  codeLocked,
  disabled,
  testIdPrefix = 'app-plan-editor',
}: AppPlanEditorProps) {
  const { t } = useTranslation();
  const displayDraft = normalizePlanDraftForBilling(draft, billingType);
  const priceLocked = billingType === 'free';
  const intervalLocked = billingType !== 'subscription';

  return (
    <div className="space-y-4" data-testid={testIdPrefix}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${testIdPrefix}-code`}>{t('appStore.fields.planCode')}</Label>
          <Input
            id={`${testIdPrefix}-code`}
            value={draft.code}
            onChange={(e) => onChange({ ...draft, code: e.target.value })}
            disabled={disabled || codeLocked}
            data-testid={`${testIdPrefix}-code`}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${testIdPrefix}-name`}>{t('appStore.fields.planName')}</Label>
          <Input
            id={`${testIdPrefix}-name`}
            value={draft.name}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
            disabled={disabled}
            data-testid={`${testIdPrefix}-name`}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${testIdPrefix}-description`}>{t('appStore.fields.description')}</Label>
        <Textarea
          id={`${testIdPrefix}-description`}
          value={draft.description}
          onChange={(e) => onChange({ ...draft, description: e.target.value })}
          disabled={disabled}
          data-testid={`${testIdPrefix}-description`}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${testIdPrefix}-price`}>{t('appStore.fields.price')}</Label>
          <Input
            id={`${testIdPrefix}-price`}
            value={displayDraft.priceAmount}
            onChange={(e) => onChange({ ...draft, priceAmount: e.target.value })}
            disabled={disabled || priceLocked}
            data-testid={`${testIdPrefix}-price`}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${testIdPrefix}-interval`}>{t('appStore.fields.billingInterval')}</Label>
          <select
            id={`${testIdPrefix}-interval`}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
            value={displayDraft.billingInterval}
            onChange={(e) => onChange({ ...draft, billingInterval: e.target.value })}
            disabled={disabled || intervalLocked}
            data-testid={`${testIdPrefix}-interval`}
          >
            <option value="none">{t('appStore.billingInterval.none')}</option>
            <option value="monthly">{t('appStore.billingInterval.monthly')}</option>
          </select>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.isDefault}
          onChange={(e) => onChange({ ...draft, isDefault: e.target.checked })}
          disabled={disabled}
          data-testid={`${testIdPrefix}-default`}
        />
        {t('appStore.fields.defaultPlan')}
      </label>
      {catalog.length > 0 ? (
        <div className="space-y-3 rounded-xl border border-border p-4">
          <p className="text-sm font-medium">{t('appStore.planEntitlements')}</p>
          {catalog.map((item) => (
            <div key={item.key} className="space-y-1.5">
              <Label htmlFor={`${testIdPrefix}-ent-${item.key}`}>
                {t(`appStore.entitlementKeys.${item.key}`, { defaultValue: item.key })}
              </Label>
              <Input
                id={`${testIdPrefix}-ent-${item.key}`}
                type="number"
                min={0}
                value={draft.entitlements[item.key] ?? ''}
                onChange={(e) =>
                  onChange({
                    ...draft,
                    entitlements: { ...draft.entitlements, [item.key]: e.target.value },
                  })
                }
                disabled={disabled}
                data-testid={`${testIdPrefix}-ent-${item.key}`}
              />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
