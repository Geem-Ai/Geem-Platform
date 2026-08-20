import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatBytes } from '@/lib/dates';
import { entitlementValueAsNumber, formatInteger } from '@/lib/format';
import { getErrorMessage } from '@/services/api/errors';
import {
  assignWorkspaceSubscription,
  fetchPlatformPlans,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformEntitlementItem, PlatformPlanListItem } from '@/services/api/types';

type AssignPlanDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  currentPlanId?: string | null;
  currentEntitlements: PlatformEntitlementItem[];
  onAssigned: () => void;
};

export function AssignPlanDialog({
  open,
  onOpenChange,
  workspaceId,
  currentPlanId,
  currentEntitlements,
  onAssigned,
}: AssignPlanDialogProps) {
  const { t, i18n } = useTranslation();
  const [planId, setPlanId] = useState('');
  const [reason, setReason] = useState('');

  const plansQuery = useQuery({
    queryKey: platformQueryKeys.plans({ status: 'active', limit: 100, offset: 0 }),
    queryFn: () => fetchPlatformPlans({ status: 'active', limit: 100, offset: 0 }),
    enabled: open,
  });

  const selectedPlan: PlatformPlanListItem | undefined = useMemo(
    () => plansQuery.data?.items.find((p) => p.id === planId),
    [plansQuery.data, planId],
  );

  const comparisonKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const item of currentEntitlements) keys.add(item.key);
    for (const item of selectedPlan?.entitlements ?? []) keys.add(item.key);
    return Array.from(keys);
  }, [currentEntitlements, selectedPlan]);

  const currentMap = useMemo(() => {
    const m = new Map<string, number | boolean | string>();
    for (const item of currentEntitlements) m.set(item.key, item.value);
    return m;
  }, [currentEntitlements]);

  const targetMap = useMemo(() => {
    const m = new Map<string, number | boolean | string>();
    for (const item of selectedPlan?.entitlements ?? []) m.set(item.key, item.value);
    return m;
  }, [selectedPlan]);

  const mutation = useMutation({
    mutationFn: () =>
      assignWorkspaceSubscription(workspaceId, { plan_id: planId, reason: reason.trim() }),
    onSuccess: () => {
      toast.success(t('billing.assignSuccess'));
      setPlanId('');
      setReason('');
      onOpenChange(false);
      onAssigned();
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const canSubmit = Boolean(planId) && reason.trim().length > 0 && planId !== currentPlanId;

  const formatEntitlement = (key: string, value: number | boolean | string | undefined) => {
    if (value == null) return '—';
    if (key === 'storage_bytes') {
      return formatBytes(entitlementValueAsNumber(value), i18n.language);
    }
    return formatInteger(entitlementValueAsNumber(value), i18n.language);
  };

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setPlanId('');
          setReason('');
        }
        onOpenChange(next);
      }}
    >
      <AlertDialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="assign-plan-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{t('billing.assignTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('billing.assignHint')}</AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-4 py-1">
          <div className="space-y-1.5">
            <Label htmlFor="assign-plan-select">{t('billing.targetPlan')}</Label>
            <select
              id="assign-plan-select"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
              value={planId}
              onChange={(e) => setPlanId(e.target.value)}
              data-testid="assign-plan-select"
            >
              <option value="">{t('billing.selectPlan')}</option>
              {(plansQuery.data?.items ?? [])
                .filter((p) => p.id !== currentPlanId && !p.is_bootstrap)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.code})
                  </option>
                ))}
            </select>
          </div>

          {selectedPlan ? (
            <div className="rounded-md border p-3 space-y-2" data-testid="assign-plan-comparison">
              <p className="text-xs font-medium text-muted-foreground">{t('billing.entitlementCompare')}</p>
              <ul className="space-y-1.5 text-sm">
                {comparisonKeys.map((key) => (
                  <li key={key} className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-3">
                    <span className="text-muted-foreground">
                      {t(`entitlements.${key}`, { defaultValue: key })}
                    </span>
                    <span className="tabular-nums sm:text-end">
                      {formatEntitlement(key, currentMap.get(key))}
                      {' → '}
                      {formatEntitlement(key, targetMap.get(key))}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted-foreground pt-1">{t('billing.noUsageReset')}</p>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="assign-plan-reason">{t('common.reasonRequired')}</Label>
            <Input
              id="assign-plan-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              placeholder={t('common.reasonPlaceholder')}
              data-testid="assign-plan-reason"
            />
          </div>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>{t('common.cancel')}</AlertDialogCancel>
          <Button
            disabled={!canSubmit || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="assign-plan-confirm"
          >
            {mutation.isPending ? t('common.working') : t('billing.assignConfirm')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
