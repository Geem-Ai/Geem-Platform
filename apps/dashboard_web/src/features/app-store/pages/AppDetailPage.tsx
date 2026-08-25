import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  AppWindow,
  ArrowLeft,
  CircleAlert,
  Layers3,
  RefreshCw,
  UsersRound,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import { GrantToWorkspacePanel } from '@/features/app-store/components/GrantToWorkspacePanel';
import {
  AppPlanEditor,
  appPlanDraftFromPlan,
  appPlanDraftToCreateBody,
  emptyAppPlanDraft,
  normalizePlanDraftForBilling,
  type AppPlanDraft,
} from '@/features/app-store/components/AppPlanEditor';
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
import { Textarea } from '@/components/ui/textarea';
import { formatMoney } from '@/lib/format';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  activatePlatformAppPlan,
  createPlatformAppPlan,
  deactivatePlatformAppPlan,
  disablePlatformApp,
  fetchPlatformApp,
  fetchPlatformAppEntitlementCatalog,
  fetchPlatformAppWorkspaces,
  platformQueryKeys,
  publishPlatformApp,
  setPlatformAppComingSoon,
  unpublishPlatformApp,
  updatePlatformApp,
  updatePlatformAppPlan,
} from '@/services/api/platform';
import type { PlatformAppDetail, PlatformAppPlanListItem } from '@/services/api/types';

type TabId = 'overview' | 'plans' | 'workspaces';
const WORKSPACES_PAGE_SIZE = 10;

export function AppDetailPage() {
  const { appId = '' } = useParams();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabId>('overview');
  const [lifecycleDialog, setLifecycleDialog] = useState<
    'publish' | 'unpublish' | 'coming_soon' | 'disable' | null
  >(null);
  const [workspaceOffset, setWorkspaceOffset] = useState(0);

  const [name, setName] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [description, setDescription] = useState('');
  const [iconUrl, setIconUrl] = useState('');
  const [sortOrder, setSortOrder] = useState('0');
  const [isFeatured, setIsFeatured] = useState(false);
  const [billingType, setBillingType] = useState('free');
  const [detailsHydrated, setDetailsHydrated] = useState(false);

  const [planDraft, setPlanDraft] = useState<AppPlanDraft | null>(null);
  const [editingPlanId, setEditingPlanId] = useState<string | null>(null);
  const [planEditReason, setPlanEditReason] = useState('');

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.app(appId),
    queryFn: () => fetchPlatformApp(appId),
    enabled: Boolean(appId),
  });

  const catalogQuery = useQuery({
    queryKey: platformQueryKeys.appEntitlementCatalog(appId),
    queryFn: () => fetchPlatformAppEntitlementCatalog(appId),
    enabled: Boolean(appId),
  });

  const workspacesQuery = useQuery({
    queryKey: platformQueryKeys.appWorkspaces(appId, {
      limit: WORKSPACES_PAGE_SIZE,
      offset: workspaceOffset,
    }),
    queryFn: () =>
      fetchPlatformAppWorkspaces(appId, {
        limit: WORKSPACES_PAGE_SIZE,
        offset: workspaceOffset,
      }),
    enabled: Boolean(appId) && tab === 'workspaces',
  });

  const hydrateDetails = useCallback((app: PlatformAppDetail) => {
    setName(app.name);
    setShortDescription(app.short_description);
    setDescription(app.description ?? '');
    setIconUrl(app.icon_url ?? '');
    setSortOrder(String(app.sort_order));
    setIsFeatured(app.is_featured);
    setBillingType(app.billing_type);
    setDetailsHydrated(true);
  }, []);

  useEffect(() => {
    if (!detailQuery.data || detailsHydrated) return;
    hydrateDetails(detailQuery.data);
  }, [detailQuery.data, detailsHydrated, hydrateDetails]);

  useEffect(() => {
    setDetailsHydrated(false);
    setWorkspaceOffset(0);
    setTab('overview');
    setPlanDraft(null);
    setEditingPlanId(null);
    setPlanEditReason('');
  }, [appId]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'apps'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.app(appId) });
    await queryClient.invalidateQueries({
      queryKey: platformQueryKeys.appWorkspaces(appId),
    });
  };

  const updateMutation = useMutation({
    mutationFn: () =>
      updatePlatformApp(appId, {
        name: name.trim(),
        short_description: shortDescription.trim(),
        description: description.trim() || null,
        icon_url: iconUrl.trim() || null,
        sort_order: Number(sortOrder) || 0,
        is_featured: isFeatured,
        billing_type: billingType,
      }),
    onSuccess: async () => {
      toast.success(t('appStore.updateSuccess'));
      setDetailsHydrated(false);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const lifecycleMutation = useMutation({
    mutationFn: ({
      action,
      reason,
    }: {
      action: NonNullable<typeof lifecycleDialog>;
      reason: string;
    }) => {
      const body = { reason };
      switch (action) {
        case 'publish':
          return publishPlatformApp(appId, body);
        case 'unpublish':
          return unpublishPlatformApp(appId, body);
        case 'coming_soon':
          return setPlatformAppComingSoon(appId, body);
        case 'disable':
          return disablePlatformApp(appId, body);
      }
    },
    onSuccess: async () => {
      toast.success(t('appStore.lifecycleSuccess'));
      setLifecycleDialog(null);
      setDetailsHydrated(false);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const createPlanMutation = useMutation({
    mutationFn: (draft: AppPlanDraft) => {
      const catalog = catalogQuery.data?.items ?? [];
      const billingType = detailQuery.data?.billing_type ?? 'free';
      const normalized = normalizePlanDraftForBilling(draft, billingType);
      const entitlements = appPlanDraftToCreateBody(normalized, catalog);
      if ('errorKey' in entitlements) {
        throw new Error(t(entitlements.errorKey));
      }
      return createPlatformAppPlan(appId, {
        code: normalized.code.trim(),
        name: normalized.name.trim(),
        description: normalized.description.trim() || null,
        price_amount: normalized.priceAmount.trim() || '0.00',
        currency: 'SAR',
        billing_interval: normalized.billingInterval,
        is_default: normalized.isDefault,
        entitlements,
      });
    },
    onSuccess: async () => {
      toast.success(t('appStore.planCreateSuccess'));
      setPlanDraft(null);
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const updatePlanMutation = useMutation({
    mutationFn: ({ planId, draft }: { planId: string; draft: AppPlanDraft }) => {
      const catalog = catalogQuery.data?.items ?? [];
      const billingType = detailQuery.data?.billing_type ?? 'free';
      const normalized = normalizePlanDraftForBilling(draft, billingType);
      const entitlements = appPlanDraftToCreateBody(normalized, catalog);
      if ('errorKey' in entitlements) {
        throw new Error(t(entitlements.errorKey));
      }
      return updatePlatformAppPlan(appId, planId, {
        code: normalized.code.trim(),
        name: normalized.name.trim(),
        description: normalized.description.trim() || null,
        price_amount: normalized.priceAmount.trim() || '0.00',
        billing_interval: normalized.billingInterval,
        is_default: normalized.isDefault,
        entitlements,
        reason: planEditReason.trim() || undefined,
      });
    },
    onSuccess: async () => {
      toast.success(t('appStore.planUpdateSuccess'));
      setEditingPlanId(null);
      setPlanDraft(null);
      setPlanEditReason('');
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const activatePlanMutation = useMutation({
    mutationFn: (planId: string) => activatePlatformAppPlan(appId, planId),
    onSuccess: async () => {
      toast.success(t('appStore.planActivateSuccess'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const deactivatePlanMutation = useMutation({
    mutationFn: (planId: string) =>
      deactivatePlatformAppPlan(appId, planId, { reason: 'Deactivated from Platform Admin' }),
    onSuccess: async () => {
      toast.success(t('appStore.planDeactivateSuccess'));
      await invalidate();
    },
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  if (detailQuery.isLoading) {
    return <p className="p-8 text-sm text-muted-foreground">{t('common.loading')}</p>;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <Link to="/app-store" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
          {t('appStore.backToList')}
        </Link>
        <Card className="mt-4" data-testid="app-detail-error">
          <CardContent className="py-12 text-center text-sm text-destructive">
            {getErrorMessage(detailQuery.error, t)}
          </CardContent>
        </Card>
      </div>
    );
  }

  const app = detailQuery.data;
  const catalog = catalogQuery.data?.items ?? [];

  const startCreatePlan = () => {
    setEditingPlanId(null);
    setPlanEditReason('');
    setPlanDraft(emptyAppPlanDraft(app.billing_type));
  };

  const startEditPlan = (plan: PlatformAppPlanListItem) => {
    setEditingPlanId(plan.id);
    setPlanEditReason('');
    setPlanDraft(appPlanDraftFromPlan(plan, catalog, app.billing_type));
  };

  const editingPlan =
    editingPlanId != null ? app.plans.find((plan) => plan.id === editingPlanId) : null;
  const showPlanEntitlementReason =
    Boolean(editingPlan && editingPlan.active_entitlement_count > 0);

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="app-detail-page"
    >
      <DocumentTitle title={app.name} />

      <Link
        to="/app-store"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
        {t('appStore.backToList')}
      </Link>

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <span className="flex size-12 items-center justify-center rounded-2xl border border-primary/15 bg-background/85 text-primary">
              <AppWindow className="size-6" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                {t('appStore.detailEyebrow')}
              </p>
              <h1 className="mt-1 truncate text-2xl font-semibold md:text-3xl">{app.name}</h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="rounded-md border border-border bg-background/70 px-2 py-1 font-mono text-xs">
                  {app.slug}
                </span>
                <Badge variant="secondary" appearance="light" size="sm">
                  {t(`appStore.status.${app.status}`, { defaultValue: app.status })}
                </Badge>
                <Badge variant="info" appearance="light" size="sm">
                  {t(`appStore.billingType.${app.billing_type}`, {
                    defaultValue: app.billing_type,
                  })}
                </Badge>
                {app.is_seeded ? (
                  <Badge variant="secondary" appearance="light" size="sm">
                    {t('appStore.seeded')}
                  </Badge>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => void detailQuery.refetch()}>
              <RefreshCw className="size-3.5" aria-hidden />
              {t('common.refresh')}
            </Button>
            {app.status === 'draft' || app.status === 'coming_soon' ? (
              <Button size="sm" onClick={() => setLifecycleDialog('publish')} data-testid="app-publish-button">
                {t('appStore.publish')}
              </Button>
            ) : null}
            {app.status === 'published' ? (
              <>
                <Button size="sm" variant="outline" onClick={() => setLifecycleDialog('coming_soon')}>
                  {t('appStore.comingSoon')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setLifecycleDialog('unpublish')}>
                  {t('appStore.unpublish')}
                </Button>
              </>
            ) : null}
            {app.disable_allowed && app.status !== 'disabled' ? (
              <Button size="sm" variant="destructive" onClick={() => setLifecycleDialog('disable')}>
                {t('appStore.disable')}
              </Button>
            ) : null}
          </div>
        </div>
      </section>

      <div className="flex flex-wrap gap-2 border-b border-border pb-1" role="tablist">
        {(['overview', 'plans', 'workspaces'] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={cn(
              'rounded-md px-3 py-2 text-sm font-medium transition-colors',
              tab === id
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
            )}
            onClick={() => setTab(id)}
            data-testid={`app-detail-tab-${id}`}
          >
            {t(`appStore.tabs.${id}`)}
          </button>
        ))}
      </div>

      {tab === 'overview' ? (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle>{t('appStore.overviewTitle')}</CardTitle>
              <CardDescription>{t('appStore.overviewSubtitle')}</CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="app-detail-name">{t('appStore.fields.name')}</Label>
                <Input
                  id="app-detail-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  data-testid="app-detail-name"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-detail-billing-type">{t('appStore.fields.billingType')}</Label>
                <select
                  id="app-detail-billing-type"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  value={billingType}
                  onChange={(e) => setBillingType(e.target.value)}
                  disabled={app.billing_type_locked}
                  data-testid="app-detail-billing-type"
                >
                  <option value="free">{t('appStore.billingType.free')}</option>
                  <option value="one_time">{t('appStore.billingType.one_time')}</option>
                  <option value="subscription">{t('appStore.billingType.subscription')}</option>
                </select>
                {app.billing_type_locked ? (
                  <p className="text-xs text-muted-foreground" data-testid="app-detail-billing-type-locked">
                    {app.status !== 'draft'
                      ? t('appStore.billingTypePublishedLocked')
                      : t('appStore.billingTypeCommercialLocked')}
                  </p>
                ) : billingType === 'free' ? (
                  <p className="text-xs text-muted-foreground">{t('appStore.billingTypeFreeOverviewHint')}</p>
                ) : null}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="app-detail-short">{t('appStore.fields.shortDescription')}</Label>
              <Input
                id="app-detail-short"
                value={shortDescription}
                onChange={(e) => setShortDescription(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="app-detail-description">{t('appStore.fields.description')}</Label>
              <Textarea
                id="app-detail-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="app-detail-icon">{t('appStore.fields.iconUrl')}</Label>
                <Input id="app-detail-icon" value={iconUrl} onChange={(e) => setIconUrl(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="app-detail-sort">{t('appStore.fields.sortOrder')}</Label>
                <Input
                  id="app-detail-sort"
                  type="number"
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value)}
                />
              </div>
              <label className="flex items-end gap-2 pb-2 text-sm">
                <input
                  type="checkbox"
                  checked={isFeatured}
                  onChange={(e) => setIsFeatured(e.target.checked)}
                />
                {t('appStore.fields.featured')}
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Metric label={t('appStore.metrics.installations')} value={app.installations_count} />
              <Metric label={t('appStore.metrics.licenses')} value={app.active_licenses_count} />
              <Metric label={t('appStore.metrics.subscriptions')} value={app.active_subscriptions_count} />
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => updateMutation.mutate()}
                disabled={updateMutation.isPending}
                data-testid="app-detail-save"
              >
                {updateMutation.isPending ? t('common.working') : t('common.save')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {tab === 'plans' ? (
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle className="flex items-center gap-2">
                  <Layers3 className="size-4" aria-hidden />
                  {t('appStore.plansTitle')}
                </CardTitle>
                <CardDescription>{t('appStore.plansSubtitle')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <Button size="sm" onClick={startCreatePlan} data-testid="app-plan-create-button">
                  {t('appStore.addPlan')}
                </Button>
              </CardToolbar>
            </CardHeader>
            <CardContent className="space-y-4">
              {app.billing_type === 'free' ? (
                <p className="text-sm text-muted-foreground" data-testid="app-plans-free-hint">
                  {t('appStore.billingTypeFreePlanHint')}
                </p>
              ) : null}
              {app.plans.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('appStore.plansEmpty')}</p>
              ) : (
                app.plans.map((plan) => (
                  <div
                    key={plan.id}
                    className="rounded-xl border border-border p-4"
                    data-testid={`app-plan-row-${plan.id}`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{plan.name}</span>
                          <span className="font-mono text-xs text-muted-foreground">{plan.code}</span>
                          {plan.is_default ? (
                            <Badge variant="warning" appearance="light" size="sm">
                              {t('appStore.defaultPlan')}
                            </Badge>
                          ) : null}
                          <Badge
                            variant={plan.is_active ? 'success' : 'secondary'}
                            appearance="light"
                            size="sm"
                          >
                            {plan.is_active ? t('appStore.planActive') : t('appStore.planInactive')}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {formatMoney(plan.price_amount, plan.currency)} ·{' '}
                          {t(`appStore.billingInterval.${plan.billing_interval}`, {
                            defaultValue: plan.billing_interval,
                          })}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="outline" onClick={() => startEditPlan(plan)}>
                          {t('common.edit')}
                        </Button>
                        {plan.is_active ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => deactivatePlanMutation.mutate(plan.id)}
                            disabled={deactivatePlanMutation.isPending}
                          >
                            {t('appStore.deactivatePlan')}
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => activatePlanMutation.mutate(plan.id)}
                          >
                            {t('appStore.activatePlan')}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {planDraft ? (
            <Card data-testid="app-plan-editor-card">
              <CardHeader>
                <CardTitle>
                  {editingPlanId ? t('appStore.editPlan') : t('appStore.newPlan')}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <AppPlanEditor
                  draft={planDraft}
                  onChange={setPlanDraft}
                  catalog={catalog}
                  billingType={app.billing_type}
                />
                {showPlanEntitlementReason ? (
                  <div className="space-y-1.5">
                    <Label htmlFor="app-plan-edit-reason">{t('appStore.fields.entitlementReason')}</Label>
                    <Input
                      id="app-plan-edit-reason"
                      value={planEditReason}
                      onChange={(e) => setPlanEditReason(e.target.value)}
                      placeholder={t('appStore.entitlementReasonHint')}
                      data-testid="app-plan-edit-reason"
                    />
                    <p className="text-xs text-muted-foreground">{t('appStore.entitlementReasonHint')}</p>
                  </div>
                ) : null}
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setPlanDraft(null);
                      setEditingPlanId(null);
                      setPlanEditReason('');
                    }}
                  >
                    {t('common.cancel')}
                  </Button>
                  <Button
                    onClick={() => {
                      if (editingPlanId) {
                        updatePlanMutation.mutate({ planId: editingPlanId, draft: planDraft });
                      } else {
                        createPlanMutation.mutate(planDraft);
                      }
                    }}
                    disabled={createPlanMutation.isPending || updatePlanMutation.isPending}
                    data-testid="app-plan-save"
                  >
                    {t('common.save')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}

      {tab === 'workspaces' ? (
        <Card>
          <CardHeader>
            <CardHeading>
              <CardTitle className="flex items-center gap-2">
                <UsersRound className="size-4" aria-hidden />
                {t('appStore.workspacesTitle')}
              </CardTitle>
              <CardDescription>{t('appStore.workspacesSubtitle')}</CardDescription>
            </CardHeading>
          </CardHeader>
          <CardContent className="space-y-4">
            <GrantToWorkspacePanel
              app={app}
              onComplete={() => {
                void workspacesQuery.refetch();
                void queryClient.invalidateQueries({ queryKey: platformQueryKeys.app(appId) });
              }}
            />
            {workspacesQuery.isError ? (
              <p className="flex items-center gap-2 text-sm text-destructive">
                <CircleAlert className="size-4" aria-hidden />
                {getErrorMessage(workspacesQuery.error, t)}
              </p>
            ) : null}
            {workspacesQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
            ) : null}
            {workspacesQuery.data?.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('appStore.workspacesEmpty')}</p>
            ) : (
              workspacesQuery.data?.items.map((item) => (
                <div
                  key={item.workspace_id}
                  className="flex flex-col gap-2 rounded-xl border border-border p-4 md:flex-row md:items-center md:justify-between"
                  data-testid={`app-workspace-row-${item.workspace_id}`}
                >
                  <div>
                    <Link
                      to={`/workspaces/${item.workspace_id}`}
                      className="font-medium hover:text-primary hover:underline"
                    >
                      {item.workspace_name}
                    </Link>
                    <p className="text-xs text-muted-foreground">{item.workspace_slug}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info" appearance="light" size="sm">
                      {t(`appStore.accessStatus.${item.access_status}`, {
                        defaultValue: item.access_status,
                      })}
                    </Badge>
                    {item.plan_name ? (
                      <span className="text-xs text-muted-foreground">{item.plan_name}</span>
                    ) : null}
                  </div>
                </div>
              ))
            )}
            {workspacesQuery.data && workspacesQuery.data.total > workspacesQuery.data.limit ? (
              <AdminPagination
                total={workspacesQuery.data.total}
                limit={workspacesQuery.data.limit}
                offset={workspacesQuery.data.offset}
                onPageChange={setWorkspaceOffset}
                testId="app-workspaces-pagination"
              />
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <LifecycleDialog
        open={lifecycleDialog !== null}
        onOpenChange={(open) => !open && setLifecycleDialog(null)}
        title={
          lifecycleDialog === 'publish'
            ? t('appStore.publishTitle')
            : lifecycleDialog === 'unpublish'
              ? t('appStore.unpublishTitle')
              : lifecycleDialog === 'coming_soon'
                ? t('appStore.comingSoonTitle')
                : t('appStore.disableTitle')
        }
        description={t('appStore.lifecycleHint')}
        reasonRequired
        confirmLabel={t('common.confirm')}
        pending={lifecycleMutation.isPending}
        onConfirm={(reason) => {
          if (!lifecycleDialog) return;
          lifecycleMutation.mutate({ action: lifecycleDialog, reason });
        }}
        testId="app-lifecycle-dialog"
      />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
