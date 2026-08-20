import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  Archive,
  ArrowLeft,
  CircleAlert,
  Clock3,
  Coins,
  Layers3,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import { PlanStatusBadge } from '@/components/shared/StatusBadges';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  PlanEntitlementEditor,
  entitlementDraftFromItems,
  entitlementDraftToPayload,
  type EntitlementDraft,
} from '@/features/plans/components/PlanEntitlementEditor';
import { formatAdminDate, formatAdminDateTime, formatBytes } from '@/lib/dates';
import { entitlementValueAsNumber, formatInteger, formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  activatePlatformPlan,
  deactivatePlatformPlan,
  fetchEntitlementCatalog,
  fetchPlatformPlan,
  platformQueryKeys,
  updatePlatformPlan,
} from '@/services/api/platform';
import type {
  PlatformEntitlementCatalogItem,
  PlatformPlanDetail,
  PlatformPlanEntitlement,
} from '@/services/api/types';

export function PlanDetailPage() {
  const { planId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<'activate' | 'deactivate' | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [priceAmount, setPriceAmount] = useState('');
  const [clearPrice, setClearPrice] = useState(false);
  const [entitlements, setEntitlements] = useState<EntitlementDraft>({});
  const [reason, setReason] = useState('');
  const [detailsHydrated, setDetailsHydrated] = useState(false);
  const [entitlementsHydrated, setEntitlementsHydrated] = useState(false);

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.plan(planId),
    queryFn: () => fetchPlatformPlan(planId),
    enabled: Boolean(planId),
  });

  const catalogQuery = useQuery({
    queryKey: platformQueryKeys.entitlementCatalog,
    queryFn: fetchEntitlementCatalog,
  });

  const hydrateDetails = useCallback((plan: PlatformPlanDetail) => {
    setName(plan.name);
    setDescription(plan.description ?? '');
    setPriceAmount(plan.price_amount ?? '');
    setClearPrice(false);
    setDetailsHydrated(true);
  }, []);

  const hydrateEntitlements = useCallback(
    (plan: PlatformPlanDetail, catalog: PlatformEntitlementCatalogItem[]) => {
      setEntitlements(entitlementDraftFromItems(catalog, plan.entitlements));
      setEntitlementsHydrated(true);
    },
    [],
  );

  useEffect(() => {
    if (!detailQuery.data || detailsHydrated) return;
    hydrateDetails(detailQuery.data);
  }, [detailQuery.data, detailsHydrated, hydrateDetails]);

  useEffect(() => {
    if (
      !detailQuery.data ||
      !catalogQuery.data?.items.length ||
      entitlementsHydrated
    ) {
      return;
    }
    hydrateEntitlements(detailQuery.data, catalogQuery.data.items);
  }, [
    catalogQuery.data,
    detailQuery.data,
    entitlementsHydrated,
    hydrateEntitlements,
  ]);

  useEffect(() => {
    setDetailsHydrated(false);
    setEntitlementsHydrated(false);
  }, [planId]);

  const originalEntitlementSignature = useMemo(() => {
    if (!detailQuery.data) return '';
    return JSON.stringify(
      detailQuery.data.entitlements
        .map((item) => [item.key, entitlementValueAsNumber(item.value)])
        .sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
    );
  }, [detailQuery.data]);

  const draftsDirty = useMemo(() => {
    const plan = detailQuery.data;
    if (!plan || !detailsHydrated) return false;

    const detailsChanged =
      name !== plan.name ||
      description !== (plan.description ?? '') ||
      priceAmount !== (plan.price_amount ?? '') ||
      clearPrice;
    const catalog = catalogQuery.data?.items;
    const entitlementsChanged =
      Boolean(catalog?.length && entitlementsHydrated) &&
      JSON.stringify(entitlements) !==
        JSON.stringify(entitlementDraftFromItems(catalog ?? [], plan.entitlements));

    return detailsChanged || entitlementsChanged || Boolean(reason);
  }, [
    catalogQuery.data,
    clearPrice,
    description,
    detailQuery.data,
    detailsHydrated,
    entitlements,
    entitlementsHydrated,
    name,
    priceAmount,
    reason,
  ]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'plans'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.plan(planId) });
  };

  const updateMutation = useMutation({
    mutationFn: (body: Parameters<typeof updatePlatformPlan>[1]) => updatePlatformPlan(planId, body),
    onSuccess: async () => {
      await invalidate();
      setDetailsHydrated(false);
      setEntitlementsHydrated(false);
      setReason('');
      toast.success(t('plans.updateSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const activateMutation = useMutation({
    mutationFn: (nextReason: string) => activatePlatformPlan(planId, nextReason),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      setDetailsHydrated(false);
      setEntitlementsHydrated(false);
      toast.success(t('plans.activateSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const deactivateMutation = useMutation({
    mutationFn: (nextReason: string) => deactivatePlatformPlan(planId, nextReason),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      setDetailsHydrated(false);
      setEntitlementsHydrated(false);
      toast.success(t('plans.deactivateSuccess'));
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const refreshPage = async () => {
    if (draftsDirty && !window.confirm(t('plans.discardChangesConfirm'))) {
      return;
    }

    const [detailResult, catalogResult] = await Promise.all([
      detailQuery.refetch(),
      catalogQuery.refetch(),
    ]);
    if (!detailResult.data) return;

    hydrateDetails(detailResult.data);
    if (catalogResult.data?.items.length) {
      hydrateEntitlements(detailResult.data, catalogResult.data.items);
    } else {
      setEntitlementsHydrated(false);
    }
    setReason('');
  };

  if (detailQuery.isLoading && !detailQuery.data) {
    return <PlanDetailSkeleton />;
  }

  if (!detailQuery.data) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8">
        <DocumentTitle title={t('plans.title')} />
        <BackToPlans />
        <Card role="alert" data-testid="plan-detail-error">
          <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">
            <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <CircleAlert className="size-5" aria-hidden />
            </span>
            <h1 className="text-base font-semibold">{t('plans.detailErrorTitle')}</h1>
            <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
              {getErrorMessage(detailQuery.error, t)}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-5"
              onClick={() => void detailQuery.refetch()}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              {t('common.retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const plan = detailQuery.data;
  const catalog = catalogQuery.data?.items ?? [];
  const catalogUnavailable = catalog.length === 0;
  const isActive = plan.status === 'active';
  const isArchived = plan.status === 'archived';
  const inUse = plan.subscriber_count > 0;
  const lifecyclePending = activateMutation.isPending || deactivateMutation.isPending;
  const pageRefreshing = detailQuery.isFetching || catalogQuery.isFetching;
  const backgroundError = detailQuery.isError
    ? { title: t('plans.detailErrorTitle'), error: detailQuery.error }
    : catalogQuery.isError && !catalogUnavailable
      ? { title: t('plans.catalogErrorTitle'), error: catalogQuery.error }
      : null;

  const onSave = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      toast.error(t('plans.nameRequired'));
      return;
    }
    if (!clearPrice && !isValidOptionalPrice(priceAmount)) {
      toast.error(t('plans.priceInvalid'));
      return;
    }
    let payload: ReturnType<typeof entitlementDraftToPayload> | undefined;
    let entitlementsChanged = false;
    if (!catalogUnavailable && entitlementsHydrated) {
      payload = entitlementDraftToPayload(catalog, entitlements);
      if ('errorKey' in payload) {
        toast.error(t(payload.errorKey));
        return;
      }
      const nextSignature = JSON.stringify(
        payload
          .map((item) => [item.key, item.value] as const)
          .sort((a, b) => a[0].localeCompare(b[0])),
      );
      entitlementsChanged = nextSignature !== originalEntitlementSignature;
    }
    if (entitlementsChanged && inUse && !reason.trim()) {
      toast.error(t('plans.reasonRequiredInUse'));
      return;
    }
    updateMutation.mutate({
      name: name.trim(),
      description: description.trim() || null,
      price_amount: clearPrice ? null : priceAmount.trim() || null,
      clear_price: clearPrice,
      currency: 'SAR',
      entitlements: entitlementsChanged && payload && !('errorKey' in payload) ? payload : undefined,
      reason: entitlementsChanged && inUse ? reason.trim() : reason.trim() || null,
    });
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="plan-detail-page"
    >
      <DocumentTitle title={plan.name} />
      <BackToPlans />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-20 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-primary/15 bg-background/85 text-primary shadow-xs md:size-14">
              <Layers3 className="size-6" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
                {t('plans.detailEyebrow')}
              </p>
              <h1 className="mt-1 break-words text-2xl font-semibold tracking-tight md:text-3xl">
                {plan.name}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span
                  className="min-w-0 max-w-full rounded-md border border-border bg-background/70 px-2 py-1 font-mono text-xs text-muted-foreground"
                  title={plan.code}
                >
                  <bdi dir="ltr" className="block truncate">{plan.code}</bdi>
                </span>
                <PlanStatusBadge status={plan.status} />
                {plan.is_bootstrap ? (
                  <Badge variant="info" appearance="light" size="sm" data-testid="plan-bootstrap-badge">
                    <ShieldCheck className="size-3" aria-hidden />
                    {t('plans.bootstrap')}
                  </Badge>
                ) : null}
                {plan.is_commercial ? (
                  <Badge variant="secondary" appearance="light" size="sm">
                    {t('plans.commercial')}
                  </Badge>
                ) : null}
              </div>
              <p className="mt-3 max-w-2xl break-words text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">
                {plan.description || t('plans.noDescription')}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void refreshPage()}
              disabled={pageRefreshing || lifecyclePending}
              className="bg-background/80"
            >
              <RefreshCw className={cn('size-4', pageRefreshing && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            {isArchived ? (
              <Button
                onClick={() => setDialog('activate')}
                disabled={lifecyclePending}
                data-testid="plan-activate-button"
              >
                <PlayCircle className="size-4" aria-hidden />
                {t('plans.activate')}
              </Button>
            ) : null}
            {isActive && !plan.is_bootstrap ? (
              <Button
                variant="destructive"
                onClick={() => setDialog('deactivate')}
                disabled={lifecyclePending}
                data-testid="plan-deactivate-button"
              >
                <PauseCircle className="size-4" aria-hidden />
                {t('plans.deactivate')}
              </Button>
            ) : null}
          </div>
        </div>

        {isActive && plan.is_bootstrap ? (
          <div
            className="relative mt-5 flex items-start gap-3 rounded-xl border border-violet-200 bg-violet-50/80 p-3.5 text-violet-950 dark:border-violet-900 dark:bg-violet-950/45 dark:text-violet-100"
            data-testid="plan-bootstrap-protected"
          >
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div>
              <p className="text-sm font-semibold">{t('plans.bootstrapProtectedTitle')}</p>
              <p className="mt-0.5 text-xs leading-5 opacity-75">{t('plans.bootstrapProtected')}</p>
            </div>
          </div>
        ) : null}

        {isArchived ? (
          <div className="relative mt-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50/90 p-3.5 text-amber-950 dark:border-amber-900 dark:bg-amber-950/45 dark:text-amber-100">
            <Archive className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div>
              <p className="text-sm font-semibold">{t('plans.archivedNoticeTitle')}</p>
              <p className="mt-0.5 text-xs leading-5 opacity-75">{t('plans.archivedNoticeHint')}</p>
            </div>
          </div>
        ) : null}
      </section>

      {backgroundError ? (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-destructive">{backgroundError.title}</p>
            <p className="mt-1 break-words text-xs text-muted-foreground">
              {getErrorMessage(backgroundError.error, t)}
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refreshPage()}>
            <RefreshCw className="size-3.5" aria-hidden />
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={t('plans.resourceSummary')}
        data-testid="plan-resource-summary"
      >
        <PlanMetric
          icon={Coins}
          label={t('plans.price')}
          value={<bdi dir="ltr">{formatMoney(plan.price_amount, plan.currency)}</bdi>}
          hint={t('plans.metricHints.price')}
          tone="primary"
        />
        <PlanMetric
          icon={UsersRound}
          label={t('plans.subscribers')}
          value={plan.subscriber_count.toLocaleString(i18n.language)}
          hint={t('plans.metricHints.subscribers')}
          tone="info"
        />
        <PlanMetric
          icon={Sparkles}
          label={t('plans.entitlements')}
          value={plan.entitlements.length.toLocaleString(i18n.language)}
          hint={t('plans.metricHints.entitlements')}
          tone="success"
        />
        <PlanMetric
          icon={Clock3}
          label={t('plans.updated')}
          value={formatAdminDate(plan.updated_at, i18n.language)}
          hint={t('plans.metricHints.updated')}
          tone="neutral"
        />
      </section>

      <div className="grid items-stretch gap-5 xl:grid-cols-[minmax(320px,0.7fr)_minmax(0,1.3fr)]">
        <Card className="h-full">
          <CardHeader className="items-start py-5 md:px-6">
            <CardHeading>
              <CardTitle>{t('plans.overview')}</CardTitle>
              <CardDescription>{t('plans.profileDescription')}</CardDescription>
            </CardHeading>
            <CardToolbar>
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Layers3 className="size-4" aria-hidden />
              </span>
            </CardToolbar>
          </CardHeader>
          <CardContent className="grid gap-x-8 gap-y-7 px-5 py-6 sm:grid-cols-2 md:px-6 md:py-7">
            <DefinitionItem
              label={t('plans.code')}
              value={
                <bdi dir="ltr" className="font-mono text-sm">
                  {plan.code}
                </bdi>
              }
            />
            <DefinitionItem
              label={t('plans.currency')}
              value={
                <bdi dir="ltr" className="font-mono text-sm">
                  {plan.currency}
                </bdi>
              }
            />
            <DefinitionItem
              label={t('plans.created')}
              value={formatAdminDateTime(plan.created_at, i18n.language)}
            />
            <DefinitionItem
              label={t('plans.updated')}
              value={formatAdminDateTime(plan.updated_at, i18n.language)}
            />
          </CardContent>
        </Card>

        <Card className="h-full">
          <CardHeader className="items-start py-5 md:px-6">
            <CardHeading>
              <CardTitle>{t('plans.currentEntitlements')}</CardTitle>
              <CardDescription>{t('plans.currentEntitlementsDescription')}</CardDescription>
            </CardHeading>
            <CardToolbar>
              <Badge variant="secondary" appearance="light">
                {t('plans.entitlementsCount', {
                  count: plan.entitlements.length,
                  formattedCount: plan.entitlements.length.toLocaleString(i18n.language),
                })}
              </Badge>
            </CardToolbar>
          </CardHeader>
          <CardContent className="px-5 py-6 md:px-6 md:py-7" data-testid="plan-entitlements-readonly">
            {plan.entitlements.length === 0 ? (
              <div className="flex min-h-32 items-center justify-center rounded-xl border border-dashed text-sm text-muted-foreground">
                {t('plans.noEntitlements')}
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {plan.entitlements.map((item) => (
                  <EntitlementSummary
                    key={item.key}
                    item={item}
                    catalogItem={catalog.find((candidate) => candidate.key === item.key)}
                    locale={i18n.language}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <form onSubmit={onSave} className="space-y-5" aria-busy={updateMutation.isPending}>
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(340px,0.75fr)_minmax(0,1.25fr)]">
          <Card>
            <CardHeader className="items-start py-5 md:px-6">
              <CardHeading>
                <CardTitle>{t('plans.editDetails')}</CardTitle>
                <CardDescription>{t('plans.editDetailsDescription')}</CardDescription>
              </CardHeading>
            </CardHeader>
            <CardContent className="space-y-5 px-5 py-6 md:px-6 md:py-7">
              <div className="space-y-1.5">
                <Label htmlFor="plan-edit-name">{t('plans.name')}</Label>
                <Input
                  id="plan-edit-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  required
                  disabled={updateMutation.isPending}
                  data-testid="plan-name-input"
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="plan-edit-description">{t('plans.description')}</Label>
                  <span className="text-[11px] tabular-nums text-muted-foreground">
                    <bdi dir="ltr">{description.length}/2000</bdi>
                  </span>
                </div>
                <textarea
                  id="plan-edit-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  maxLength={2000}
                  rows={4}
                  disabled={updateMutation.isPending}
                  className="flex w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="plan-description-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-edit-price">{t('plans.price')}</Label>
                <Input
                  id="plan-edit-price"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  dir="ltr"
                  value={priceAmount}
                  onChange={(event) => {
                    setPriceAmount(event.target.value);
                    setClearPrice(false);
                  }}
                  disabled={clearPrice || updateMutation.isPending}
                  placeholder={t('plans.pricePlaceholder')}
                  aria-describedby="plan-edit-price-hint"
                  className="font-mono tabular-nums"
                  data-testid="plan-price-input"
                />
                <p id="plan-edit-price-hint" className="text-xs leading-5 text-muted-foreground">
                  {t('plans.priceInputHint')}
                </p>
              </div>
              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-muted/20 p-3.5 text-sm transition-colors hover:bg-muted/35">
                <input
                  type="checkbox"
                  checked={clearPrice}
                  onChange={(event) => setClearPrice(event.target.checked)}
                  disabled={updateMutation.isPending}
                  className="mt-0.5 size-4 shrink-0 accent-primary"
                  data-testid="plan-clear-price"
                />
                <span className="leading-5">{t('plans.clearPrice')}</span>
              </label>
              <div className="space-y-1.5">
                <Label htmlFor="plan-edit-currency">{t('plans.currency')}</Label>
                <Input
                  id="plan-edit-currency"
                  value="SAR"
                  readOnly
                  dir="ltr"
                  className="bg-muted/35 font-mono"
                  data-testid="plan-currency-input"
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="items-start py-5 md:px-6">
              <CardHeading>
                <CardTitle>{t('plans.editEntitlements')}</CardTitle>
                <CardDescription>{t('plans.editEntitlementsDescription')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <Badge variant="secondary" appearance="light">
                  {t('plans.entitlementsCount', {
                    count: catalog.length,
                    formattedCount: catalog.length.toLocaleString(i18n.language),
                  })}
                </Badge>
              </CardToolbar>
            </CardHeader>
            <CardContent className="space-y-6 px-5 py-6 md:px-6 md:py-7">
              {catalogQuery.isLoading && !catalogQuery.data ? (
                <div className="space-y-3" role="status" aria-live="polite">
                  <span className="sr-only">{t('common.loading')}</span>
                  <div className="h-24 animate-pulse rounded-xl bg-muted" aria-hidden />
                  <div className="h-24 animate-pulse rounded-xl bg-muted" aria-hidden />
                </div>
              ) : catalogUnavailable ? (
                <div
                  className="flex min-h-52 flex-col items-center justify-center rounded-xl border border-dashed px-5 py-8 text-center"
                  role="alert"
                  data-testid="plan-detail-catalog-error"
                >
                  <span className="mb-3 flex size-10 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                    <CircleAlert className="size-4" aria-hidden />
                  </span>
                  <p className="text-sm font-semibold">{t('plans.catalogErrorTitle')}</p>
                  <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
                    {catalogQuery.isError
                      ? getErrorMessage(catalogQuery.error, t)
                      : t('plans.catalogErrorHint')}
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    onClick={() => void catalogQuery.refetch()}
                    disabled={catalogQuery.isFetching}
                  >
                    <RefreshCw
                      className={cn('size-3.5', catalogQuery.isFetching && 'animate-spin')}
                      aria-hidden
                    />
                    {t('common.retry')}
                  </Button>
                </div>
              ) : (
                <>
                  <PlanEntitlementEditor
                    catalog={catalog}
                    values={entitlements}
                    onChange={setEntitlements}
                    disabled={updateMutation.isPending}
                  />
                  {inUse ? (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900 dark:bg-amber-950/30">
                      <div className="flex items-center justify-between gap-3">
                        <Label htmlFor="plan-edit-reason">{t('plans.reasonInUse')}</Label>
                        <span className="text-[11px] tabular-nums text-muted-foreground">
                          <bdi dir="ltr">{reason.length}/500</bdi>
                        </span>
                      </div>
                      <textarea
                        id="plan-edit-reason"
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                        maxLength={500}
                        rows={3}
                        disabled={updateMutation.isPending}
                        placeholder={t('common.reasonPlaceholder')}
                        aria-describedby="plan-edit-reason-hint"
                        className="mt-2 flex w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="plan-edit-reason"
                      />
                      <p id="plan-edit-reason-hint" className="mt-2 text-xs leading-5 text-muted-foreground">
                        {t('plans.reasonInUseHint')}
                      </p>
                    </div>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="flex justify-end rounded-xl border border-border bg-card p-4 shadow-xs">
          <Button
            type="submit"
            disabled={updateMutation.isPending}
            data-testid="plan-save-button"
          >
            {updateMutation.isPending ? t('common.working') : t('plans.save')}
          </Button>
        </div>
      </form>

      <LifecycleDialog
        open={dialog === 'activate'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('plans.activateTitle')}
        description={t('plans.activateHint')}
        reasonRequired
        confirmLabel={t('plans.activate')}
        confirmVariant="primary"
        pending={activateMutation.isPending}
        onConfirm={(nextReason) => activateMutation.mutate(nextReason)}
        testId="plan-activate-dialog"
      />
      <LifecycleDialog
        open={dialog === 'deactivate'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('plans.deactivateTitle')}
        description={t('plans.deactivateHint')}
        reasonRequired
        confirmLabel={t('plans.deactivate')}
        pending={deactivateMutation.isPending}
        onConfirm={(nextReason) => deactivateMutation.mutate(nextReason)}
        testId="plan-deactivate-dialog"
      />
    </div>
  );
}

type MetricTone = 'primary' | 'success' | 'info' | 'neutral';

function PlanMetric({
  icon: Icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  hint: string;
  tone: MetricTone;
}) {
  const tones: Record<MetricTone, string> = {
    primary: 'bg-primary/10 text-primary',
    success: 'bg-green-100 text-green-700 dark:bg-green-950/70 dark:text-green-300',
    info: 'bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300',
    neutral: 'bg-muted text-muted-foreground',
  };

  return (
    <Card className="min-h-28">
      <CardContent className="flex items-center gap-4 p-4">
        <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-xl', tones[tone])}>
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold tabular-nums">{value}</p>
          <p className="truncate text-xs font-medium">{label}</p>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function EntitlementSummary({
  item,
  catalogItem,
  locale,
}: {
  item: PlatformPlanEntitlement;
  catalogItem?: PlatformEntitlementCatalogItem;
  locale: string;
}) {
  const { t } = useTranslation();
  const isStorage = item.key === 'storage_bytes';
  const value = isStorage
    ? formatBytes(entitlementValueAsNumber(item.value), locale)
    : formatInteger(entitlementValueAsNumber(item.value), locale);
  const unit = isStorage
    ? t('entitlements.storageInputHint')
    : catalogItem
      ? t(`entitlements.units.${catalogItem.unit}`, { defaultValue: catalogItem.unit })
      : '';

  return (
    <div className="rounded-xl border border-border bg-muted/15 p-4">
      <p className="truncate text-xs font-medium text-muted-foreground">
        {t(`entitlements.${item.key}`, { defaultValue: item.key })}
      </p>
      <p className="mt-2 truncate text-base font-semibold tabular-nums">
        <bdi dir="ltr">{value}</bdi>
      </p>
      {unit ? <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{unit}</p> : null}
    </div>
  );
}

function DefinitionItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-2 min-w-0 break-words text-sm font-medium leading-6">{value}</div>
    </div>
  );
}

function BackToPlans() {
  const { t } = useTranslation();
  return (
    <Link
      to="/plans"
      className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
    >
      <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
      {t('plans.backToList')}
    </Link>
  );
}

function PlanDetailSkeleton() {
  const { t } = useTranslation();
  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      aria-busy="true"
      aria-live="polite"
      role="status"
      data-testid="plan-detail-loading"
    >
      <span className="sr-only">{t('common.loading')}</span>
      <div className="h-5 w-36 animate-pulse rounded bg-muted" />
      <div className="h-48 animate-pulse rounded-2xl bg-muted" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-28 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
      </div>
      <div className="h-96 animate-pulse rounded-xl bg-muted" />
    </div>
  );
}

function isValidOptionalPrice(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  const amount = Number(trimmed);
  return Number.isFinite(amount) && amount >= 0;
}
