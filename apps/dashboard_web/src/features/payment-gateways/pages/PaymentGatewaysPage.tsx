import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { CreditCard, RefreshCw, SearchX } from 'lucide-react';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { GatewayConfigDialog } from '@/features/payment-gateways/components/GatewayConfigDialog';
import { formatAdminDate } from '@/lib/dates';
import { getErrorMessage } from '@/services/api/errors';
import {
  activatePlatformPaymentGateway,
  createPlatformPaymentGateway,
  fetchPlatformPaymentGateways,
  platformQueryKeys,
  updatePlatformPaymentGateway,
} from '@/services/api/platform';
import type { PlatformPaymentGatewayListItem } from '@/services/api/types';

export function PaymentGatewaysPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [configTarget, setConfigTarget] = useState<PlatformPaymentGatewayListItem | null>(null);
  const [activateTarget, setActivateTarget] = useState<PlatformPaymentGatewayListItem | null>(null);

  const query = useQuery({
    queryKey: platformQueryKeys.paymentGateways,
    queryFn: fetchPlatformPaymentGateways,
  });

  const saveMutation = useMutation({
    mutationFn: async (values: { profileId: string; serverKey: string; testMode: boolean }) => {
      if (!configTarget) return;
      if (!configTarget.id) {
        return createPlatformPaymentGateway({
          code: configTarget.code,
          test_mode: values.testMode,
          credentials: {
            profile_id: values.profileId,
            ...(values.serverKey ? { server_key: values.serverKey } : {}),
          },
        });
      }
      return updatePlatformPaymentGateway(configTarget.id, {
        test_mode: values.testMode,
        profile_id: values.profileId,
        credentials: values.serverKey ? { server_key: values.serverKey } : undefined,
      });
    },
    onSuccess: () => {
      toast.success(
        configTarget?.id ? t('paymentGateways.updateSuccess') : t('paymentGateways.createSuccess'),
      );
      setConfigTarget(null);
      void queryClient.invalidateQueries({ queryKey: platformQueryKeys.paymentGateways });
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const activateMutation = useMutation({
    mutationFn: async (reason: string) => {
      if (!activateTarget?.id) return;
      return activatePlatformPaymentGateway(activateTarget.id, reason);
    },
    onSuccess: () => {
      toast.success(t('paymentGateways.activateSuccess'));
      setActivateTarget(null);
      void queryClient.invalidateQueries({ queryKey: platformQueryKeys.paymentGateways });
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const items = useMemo(() => query.data?.items ?? [], [query.data?.items]);

  return (
    <div
      className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 p-5 md:p-8"
      data-testid="payment-gateways-page"
    >
      <DocumentTitle title={t('paymentGateways.title')} />

      <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            {t('paymentGateways.eyebrow')}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            {t('paymentGateways.title')}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            {t('paymentGateways.subtitle')}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          <RefreshCw className="size-4" aria-hidden />
          {t('common.refresh')}
        </Button>
      </section>

      {query.isLoading ? (
        <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
      ) : query.isError ? (
        <p className="text-sm text-destructive">{getErrorMessage(query.error, t)}</p>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground" data-testid="payment-gateways-empty">
          <SearchX className="size-8 opacity-60" aria-hidden />
          <p>{t('paymentGateways.empty')}</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2" data-testid="payment-gateways-list">
          {items.map((gateway) => (
            <Card key={gateway.code} data-testid={`gateway-card-${gateway.code}`}>
              <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
                <div className="flex items-start gap-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <CreditCard className="size-5" aria-hidden />
                  </span>
                  <div>
                    <CardTitle className="text-base">{gateway.display_name}</CardTitle>
                    <p className="text-xs text-muted-foreground font-mono">{gateway.code}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1 justify-end">
                  {gateway.enabled ? (
                    <Badge data-testid={`gateway-active-${gateway.code}`}>{t('paymentGateways.active')}</Badge>
                  ) : (
                    <Badge variant="outline">{t('paymentGateways.inactive')}</Badge>
                  )}
                  {gateway.configured ? (
                    <Badge variant="secondary">{t('paymentGateways.configured')}</Badge>
                  ) : (
                    <Badge variant="outline">{t('paymentGateways.notConfigured')}</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {gateway.test_mode != null ? (
                  <p className="text-muted-foreground">
                    {gateway.test_mode ? t('paymentGateways.testMode') : t('paymentGateways.liveMode')}
                  </p>
                ) : null}
                {gateway.id ? (
                  <>
                    <p className="text-muted-foreground">
                      {t('paymentGateways.referenced', { count: gateway.referenced_purchases_count })}
                    </p>
                    {gateway.in_flight_purchases_count > 0 ? (
                      <p className="text-amber-600 dark:text-amber-400">
                        {t('paymentGateways.inFlight', { count: gateway.in_flight_purchases_count })}
                      </p>
                    ) : null}
                    {gateway.updated_at ? (
                      <p className="text-xs text-muted-foreground">
                        {formatAdminDate(gateway.updated_at, i18n.language)}
                      </p>
                    ) : null}
                  </>
                ) : null}
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setConfigTarget(gateway)}
                    data-testid={`gateway-configure-${gateway.code}`}
                  >
                    {gateway.id ? t('paymentGateways.configure') : t('paymentGateways.addConfiguration')}
                  </Button>
                  {gateway.id && gateway.configured && !gateway.enabled ? (
                    <Button
                      size="sm"
                      onClick={() => setActivateTarget(gateway)}
                      data-testid={`gateway-activate-${gateway.code}`}
                    >
                      {t('paymentGateways.setActive')}
                    </Button>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <GatewayConfigDialog
        open={configTarget !== null}
        onOpenChange={(open) => !open && setConfigTarget(null)}
        gateway={configTarget}
        pending={saveMutation.isPending}
        onSubmit={(values) => saveMutation.mutate(values)}
      />

      <LifecycleDialog
        open={activateTarget !== null}
        onOpenChange={(open) => !open && setActivateTarget(null)}
        title={t('paymentGateways.activateTitle')}
        description={t('paymentGateways.activateDescription')}
        reasonRequired
        confirmLabel={t('paymentGateways.activateConfirm')}
        confirmVariant="primary"
        pending={activateMutation.isPending}
        onConfirm={(reason) => activateMutation.mutate(reason)}
        testId="gateway-activate-dialog"
      />
    </div>
  );
}
