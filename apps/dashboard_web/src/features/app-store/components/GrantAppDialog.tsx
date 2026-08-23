import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { AppWindow } from 'lucide-react';
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
import { getErrorMessage } from '@/services/api/errors';
import {
  extendPlatformAppSubscription,
  grantPlatformAppLicense,
  grantPlatformAppSubscription,
  newAppGrantIdempotencyKey,
  revokePlatformAppLicense,
  revokePlatformAppSubscription,
} from '@/services/api/platform';
import type { PlatformAppPlanListItem, PlatformWorkspaceApp } from '@/services/api/types';

type GrantAppDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  workspaceName?: string;
  app: PlatformWorkspaceApp | null;
  plans: PlatformAppPlanListItem[];
  mode: 'grant' | 'revoke' | 'extend';
  onComplete: () => void;
};

export function GrantAppDialog({
  open,
  onOpenChange,
  workspaceId,
  workspaceName,
  app,
  plans,
  mode,
  onComplete,
}: GrantAppDialogProps) {
  const { t } = useTranslation();
  const [planId, setPlanId] = useState('');
  const [reason, setReason] = useState('');
  const idempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPlanId('');
      setReason('');
      idempotencyKeyRef.current = null;
      return;
    }
    idempotencyKeyRef.current = newAppGrantIdempotencyKey();
    if (plans.length === 1) {
      setPlanId(plans[0].id);
    }
  }, [open, plans]);

  const billingType = app?.billing_type ?? 'free';
  const isGrant = mode === 'grant';
  const isExtend = mode === 'extend';
  const reasonValid = reason.trim().length > 0;
  const planValid = billingType === 'free' || planId.length > 0;
  const canSubmit = reasonValid && (isGrant ? planValid : true);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!app) throw new Error('Missing app');
      const trimmedReason = reason.trim();
      if (isExtend) {
        const idempotencyKey = idempotencyKeyRef.current ?? newAppGrantIdempotencyKey();
        return extendPlatformAppSubscription(workspaceId, app.app_id, {
          reason: trimmedReason,
          idempotency_key: idempotencyKey,
        });
      }
      if (isGrant) {
        const idempotencyKey = idempotencyKeyRef.current ?? newAppGrantIdempotencyKey();
        if (billingType === 'one_time') {
          return grantPlatformAppLicense(workspaceId, app.app_id, {
            app_plan_id: planId,
            reason: trimmedReason,
            idempotency_key: idempotencyKey,
          });
        }
        if (billingType === 'subscription') {
          return grantPlatformAppSubscription(workspaceId, app.app_id, {
            app_plan_id: planId,
            reason: trimmedReason,
            idempotency_key: idempotencyKey,
          });
        }
        throw new Error('Free apps do not require grants');
      }
      if (billingType === 'one_time') {
        return revokePlatformAppLicense(workspaceId, app.app_id, { reason: trimmedReason });
      }
      if (billingType === 'subscription') {
        return revokePlatformAppSubscription(workspaceId, app.app_id, { reason: trimmedReason });
      }
      throw new Error('Nothing to revoke');
    },
    onSuccess: (res) => {
      toast.success(
        res.idempotent_replay ? t('appStore.grantReplay') : t('appStore.grantSuccess'),
      );
      onOpenChange(false);
      onComplete();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  if (!app) return null;

  const activePlans = plans.filter((p) => p.is_active);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="grant-app-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>
            {isGrant
              ? t('appStore.grantTitle')
              : isExtend
                ? t('appStore.extendTitle')
                : t('appStore.revokeTitle')}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {workspaceName
              ? t('appStore.grantHintNamed', { workspace: workspaceName, app: app.app_name })
              : t('appStore.grantHint', { app: app.app_name })}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-4 py-2">
          <div className="flex items-center gap-3 rounded-lg border border-border p-3">
            <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <AppWindow className="size-4" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{app.app_name}</p>
              <p className="text-xs text-muted-foreground">{app.app_slug}</p>
            </div>
          </div>

          {isGrant && billingType !== 'free' ? (
            <div className="space-y-1.5">
              <Label htmlFor="grant-app-plan">{t('appStore.fields.plan')}</Label>
              <select
                id="grant-app-plan"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={planId}
                onChange={(e) => setPlanId(e.target.value)}
                data-testid="grant-app-plan"
              >
                <option value="">{t('appStore.selectPlan')}</option>
                {activePlans.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name} ({plan.code})
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="grant-app-reason">{t('appStore.fields.reason')}</Label>
            <Input
              id="grant-app-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              data-testid="grant-app-reason"
            />
          </div>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>{t('common.cancel')}</AlertDialogCancel>
          <Button
            variant={isGrant || isExtend ? 'primary' : 'destructive'}
            disabled={!canSubmit || mutation.isPending}
            onClick={() => mutation.mutate()}
            data-testid="grant-app-confirm"
          >
            {mutation.isPending
              ? t('common.working')
              : isGrant
                ? t('appStore.grant')
                : isExtend
                  ? t('appStore.extend')
                  : t('appStore.revoke')}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
