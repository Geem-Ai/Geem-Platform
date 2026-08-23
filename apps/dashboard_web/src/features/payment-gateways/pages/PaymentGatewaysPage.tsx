import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  CheckCircle2,
  CircleAlert,
  CreditCard,
  Info,
  RefreshCw,
  SearchX,
  ShoppingBag,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { GatewayCard } from '@/features/payment-gateways/components/GatewayCard';
import { GatewayConfigDialog } from '@/features/payment-gateways/components/GatewayConfigDialog';
import { cn } from '@/lib/utils';
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
  const summary = useMemo(() => {
    const active = items.find((gateway) => gateway.enabled);
    const configured = items.filter((gateway) => gateway.configured).length;
    const totalPurchases = items.reduce(
      (sum, gateway) => sum + gateway.referenced_purchases_count,
      0,
    );
    const inFlight = items.reduce(
      (sum, gateway) => sum + gateway.in_flight_purchases_count,
      0,
    );
    return { active, configured, totalPurchases, inFlight };
  }, [items]);

  return (
    <div
      className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 p-5 md:p-8"
      data-testid="payment-gateways-page"
    >
      <DocumentTitle title={t('paymentGateways.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-16 -top-20 size-56 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10">
                <CreditCard className="size-3.5" aria-hidden />
              </span>
              {t('paymentGateways.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('paymentGateways.title')}
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
              {t('paymentGateways.subtitle')}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              className="bg-background/80"
            >
              <RefreshCw
                className={cn('size-4', query.isFetching && 'animate-spin')}
                aria-hidden
              />
              {t('common.refresh')}
            </Button>
            <Button variant="outline" asChild className="bg-background/80">
              <Link to="/purchases">
                <ShoppingBag className="size-4" aria-hidden />
                {t('paymentGateways.viewPurchases')}
              </Link>
            </Button>
          </div>
        </div>
      </section>

      {!query.isLoading && !query.isError && items.length > 0 ? (
        <section
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
          aria-label={t('paymentGateways.summary.label')}
          data-testid="gateway-summary"
        >
          <SummaryMetric
            icon={Zap}
            label={t('paymentGateways.summary.activeGateway')}
            value={summary.active?.display_name ?? t('paymentGateways.summary.noneActive')}
            loading={false}
            tone="primary"
            testId="gateway-stat-active"
          />
          <SummaryMetric
            icon={CheckCircle2}
            label={t('paymentGateways.summary.configured')}
            value={summary.configured.toLocaleString(i18n.language)}
            loading={false}
            tone="success"
            testId="gateway-stat-configured"
          />
          <SummaryMetric
            icon={ShoppingBag}
            label={t('paymentGateways.summary.totalPurchases')}
            value={summary.totalPurchases.toLocaleString(i18n.language)}
            loading={false}
            tone="info"
            testId="gateway-stat-purchases"
          />
          <SummaryMetric
            icon={CircleAlert}
            label={t('paymentGateways.summary.inFlight')}
            value={summary.inFlight.toLocaleString(i18n.language)}
            loading={false}
            tone={summary.inFlight > 0 ? 'warning' : 'info'}
            testId="gateway-stat-in-flight"
          />
        </section>
      ) : null}

      {!query.isLoading && !query.isError && items.length > 0 ? (
        <div
          className="flex gap-3 rounded-xl border border-border bg-muted/20 p-4"
          data-testid="gateway-info-banner"
        >
          <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
          <div>
            <p className="text-sm font-medium">{t('paymentGateways.infoBanner.title')}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t('paymentGateways.infoBanner.description')}
            </p>
          </div>
        </div>
      ) : null}

      {query.isLoading ? (
        <GatewayListSkeleton />
      ) : query.isError ? (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <div className="flex min-w-0 items-start gap-3">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
            <p className="text-sm text-destructive">{getErrorMessage(query.error, t)}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            <RefreshCw className="size-3.5" aria-hidden />
            {t('common.retry')}
          </Button>
        </div>
      ) : items.length === 0 ? (
        <div
          className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border py-16 text-muted-foreground"
          data-testid="payment-gateways-empty"
        >
          <SearchX className="size-8 opacity-60" aria-hidden />
          <p>{t('paymentGateways.empty')}</p>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2" data-testid="payment-gateways-list">
          {items.map((gateway) => (
            <GatewayCard
              key={gateway.code}
              gateway={gateway}
              locale={i18n.language}
              onConfigure={() => setConfigTarget(gateway)}
              onActivate={() => setActivateTarget(gateway)}
            />
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

type MetricTone = 'primary' | 'success' | 'warning' | 'info';

function SummaryMetric({
  icon: Icon,
  label,
  value,
  loading,
  tone,
  testId,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  loading: boolean;
  tone: MetricTone;
  testId: string;
}) {
  const tones: Record<MetricTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/70 dark:text-amber-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
  };

  return (
    <Card className="min-h-28" data-testid={testId}>
      <CardContent className="flex items-center justify-between gap-4 p-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? (
            <div className="mt-2 h-7 w-24 animate-pulse rounded bg-muted" />
          ) : (
            <p className="mt-1 truncate text-lg font-semibold">{value}</p>
          )}
        </div>
        <span
          className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tones[tone])}
        >
          <Icon className="size-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

function GatewayListSkeleton() {
  const { t } = useTranslation();

  return (
    <div
      className="grid gap-4 lg:grid-cols-2"
      data-testid="payment-gateways-loading"
      role="status"
      aria-label={t('common.loading')}
    >
      {Array.from({ length: 2 }).map((_, index) => (
        <Card key={index} className="overflow-hidden">
          <CardContent className="space-y-4 p-5">
            <div className="flex items-start gap-3">
              <div className="size-11 animate-pulse rounded-xl bg-muted" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-32 animate-pulse rounded bg-muted" />
                <div className="h-3 w-20 animate-pulse rounded bg-muted" />
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="h-14 animate-pulse rounded-lg bg-muted/70" />
              <div className="h-14 animate-pulse rounded-lg bg-muted/70" />
            </div>
            <div className="h-9 w-28 animate-pulse rounded-md bg-muted" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
