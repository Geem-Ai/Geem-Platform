import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import type { AppPlan, CatalogApp } from '@/services/api/apps';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { useAppCheckout, useAppRenewal } from '../hooks/useAppsQueries';

export function AppPurchaseButton({
  app,
  plan,
  canManage,
}: {
  app: CatalogApp;
  plan?: AppPlan;
  canManage: boolean;
}) {
  const { t } = useTranslation();
  const checkout = useAppCheckout();
  const renew = useAppRenewal();
  const access = app.access;
  const pending = checkout.isPending || renew.isPending;

  if (!canManage) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="app-member-hint">
        {t('apps.memberHint')}
      </p>
    );
  }

  async function onBuy() {
    if (!plan) return;
    try {
      await checkout.mutateAsync({ slug: app.slug, planId: plan.id });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'unknown';
      toast.error(t(errorMessageKey(code)));
    }
  }

  async function onRenew() {
    try {
      await renew.mutateAsync(app.slug);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : 'unknown';
      toast.error(t(errorMessageKey(code)));
    }
  }

  if (access?.can_renew) {
    return (
      <Button
        type="button"
        disabled={pending}
        data-testid="app-renew"
        onClick={() => void onRenew()}
      >
        {pending && renew.isPending ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : null}
        {t('apps.billing.renew')}
      </Button>
    );
  }

  if (access?.can_purchase && plan) {
    const label =
      app.billing_type === 'subscription'
        ? t('apps.billing.choosePlan')
        : t('apps.billing.buyAndInstall');
    return (
      <Button
        type="button"
        disabled={pending}
        data-testid={`app-buy-${plan.code}`}
        onClick={() => void onBuy()}
      >
        {pending && checkout.isPending ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : null}
        {label}
      </Button>
    );
  }

  return null;
}
