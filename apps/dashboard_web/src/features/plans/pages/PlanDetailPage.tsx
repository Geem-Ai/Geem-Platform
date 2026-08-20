import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import { PlanStatusBadge } from '@/components/shared/StatusBadges';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatAdminDateTime, formatBytes } from '@/lib/dates';
import { entitlementValueAsNumber, formatInteger, formatMoney } from '@/lib/format';
import {
  PlanEntitlementEditor,
  entitlementDraftFromItems,
  entitlementDraftToPayload,
  type EntitlementDraft,
} from '@/features/plans/components/PlanEntitlementEditor';
import { getErrorMessage } from '@/services/api/errors';
import {
  activatePlatformPlan,
  deactivatePlatformPlan,
  fetchEntitlementCatalog,
  fetchPlatformPlan,
  platformQueryKeys,
  updatePlatformPlan,
} from '@/services/api/platform';

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
  const [hydrated, setHydrated] = useState(false);

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.plan(planId),
    queryFn: () => fetchPlatformPlan(planId),
    enabled: Boolean(planId),
  });

  const catalogQuery = useQuery({
    queryKey: platformQueryKeys.entitlementCatalog,
    queryFn: fetchEntitlementCatalog,
  });

  useEffect(() => {
    if (!detailQuery.data || !catalogQuery.data || hydrated) return;
    const plan = detailQuery.data;
    setName(plan.name);
    setDescription(plan.description ?? '');
    setPriceAmount(plan.price_amount ?? '');
    setClearPrice(false);
    setEntitlements(entitlementDraftFromItems(catalogQuery.data.items, plan.entitlements));
    setHydrated(true);
  }, [detailQuery.data, catalogQuery.data, hydrated]);

  useEffect(() => {
    setHydrated(false);
  }, [planId]);

  const originalEntitlementSignature = useMemo(() => {
    if (!detailQuery.data || !catalogQuery.data) return '';
    return JSON.stringify(
      detailQuery.data.entitlements
        .map((e) => [e.key, entitlementValueAsNumber(e.value)])
        .sort((a, b) => String(a[0]).localeCompare(String(b[0]))),
    );
  }, [detailQuery.data, catalogQuery.data]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'plans'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.plan(planId) });
  };

  const updateMutation = useMutation({
    mutationFn: (body: Parameters<typeof updatePlatformPlan>[1]) => updatePlatformPlan(planId, body),
    onSuccess: async () => {
      await invalidate();
      setHydrated(false);
      setReason('');
      toast.success(t('plans.updateSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const activateMutation = useMutation({
    mutationFn: (r: string) => activatePlatformPlan(planId, r),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      setHydrated(false);
      toast.success(t('plans.activateSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const deactivateMutation = useMutation({
    mutationFn: (r: string) => deactivatePlatformPlan(planId, r),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      setHydrated(false);
      toast.success(t('plans.deactivateSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  if (detailQuery.isLoading || catalogQuery.isLoading) {
    return (
      <div className="space-y-3" data-testid="plan-detail-loading">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-40 animate-pulse rounded-md bg-muted" />
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <p className="text-sm text-destructive" data-testid="plan-detail-error">
        {getErrorMessage(detailQuery.error, t)}
      </p>
    );
  }

  const plan = detailQuery.data;
  const catalog = catalogQuery.data?.items ?? [];
  const isActive = plan.status === 'active';
  const isArchived = plan.status === 'archived';
  const inUse = plan.subscriber_count > 0;

  const onSave = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = entitlementDraftToPayload(catalog, entitlements);
    if ('errorKey' in payload) {
      toast.error(t(payload.errorKey));
      return;
    }
    const nextSig = JSON.stringify(
      payload
        .map((item) => [item.key, item.value] as const)
        .sort((a, b) => a[0].localeCompare(b[0])),
    );
    const entitlementsChanged = nextSig !== originalEntitlementSignature;
    if (entitlementsChanged && inUse && !reason.trim()) {
      toast.error(t('plans.reasonRequiredInUse'));
      return;
    }
    if (!name.trim()) {
      toast.error(t('plans.fieldsRequired'));
      return;
    }
    updateMutation.mutate({
      name: name.trim(),
      description: description.trim() || null,
      price_amount: clearPrice ? null : priceAmount.trim() || null,
      clear_price: clearPrice,
      currency: 'SAR',
      entitlements: entitlementsChanged ? payload : undefined,
      reason: entitlementsChanged && inUse ? reason.trim() : reason.trim() || null,
    });
  };

  return (
    <div className="space-y-4" data-testid="plan-detail-page">
      <DocumentTitle title={plan.name} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <Link to="/plans" className="text-xs text-muted-foreground hover:underline">
            {t('plans.backToList')}
          </Link>
          <h1 className="text-xl font-semibold tracking-tight truncate">{plan.name}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{plan.code}</span>
            <PlanStatusBadge status={plan.status} />
            {plan.is_bootstrap ? (
              <Badge variant="info" appearance="light" size="sm" data-testid="plan-bootstrap-badge">
                {t('plans.bootstrap')}
              </Badge>
            ) : null}
            {plan.is_commercial ? (
              <Badge variant="secondary" appearance="light" size="sm">
                {t('plans.commercial')}
              </Badge>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {isArchived ? (
            <Button onClick={() => setDialog('activate')} data-testid="plan-activate-button">
              {t('plans.activate')}
            </Button>
          ) : null}
          {isActive && !plan.is_bootstrap ? (
            <Button
              variant="destructive"
              onClick={() => setDialog('deactivate')}
              data-testid="plan-deactivate-button"
            >
              {t('plans.deactivate')}
            </Button>
          ) : null}
          {isActive && plan.is_bootstrap ? (
            <p className="text-xs text-muted-foreground max-w-xs" data-testid="plan-bootstrap-protected">
              {t('plans.bootstrapProtected')}
            </p>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('plans.overview')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label={t('plans.price')} value={formatMoney(plan.price_amount, plan.currency)} />
            <Row
              label={t('plans.subscribers')}
              value={String(plan.subscriber_count)}
            />
            <Row label={t('plans.created')} value={formatAdminDateTime(plan.created_at, i18n.language)} />
            <Row label={t('plans.updated')} value={formatAdminDateTime(plan.updated_at, i18n.language)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('plans.currentEntitlements')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm" data-testid="plan-entitlements-readonly">
            {plan.entitlements.map((item) => (
              <Row
                key={item.key}
                label={t(`entitlements.${item.key}`, { defaultValue: item.key })}
                value={
                  item.key === 'storage_bytes'
                    ? formatBytes(entitlementValueAsNumber(item.value), i18n.language)
                    : formatInteger(entitlementValueAsNumber(item.value), i18n.language)
                }
              />
            ))}
          </CardContent>
        </Card>
      </div>

      <form onSubmit={onSave} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('plans.editDetails')}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="plan-edit-name">{t('plans.name')}</Label>
              <Input
                id="plan-edit-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
                data-testid="plan-name-input"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="plan-edit-description">{t('plans.description')}</Label>
              <textarea
                id="plan-edit-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={2000}
                rows={3}
                className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                data-testid="plan-description-input"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="plan-edit-price">{t('plans.price')}</Label>
              <Input
                id="plan-edit-price"
                value={priceAmount}
                onChange={(e) => {
                  setPriceAmount(e.target.value);
                  setClearPrice(false);
                }}
                disabled={clearPrice}
                placeholder={t('plans.pricePlaceholder')}
                data-testid="plan-price-input"
              />
              <label className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
                <input
                  type="checkbox"
                  checked={clearPrice}
                  onChange={(e) => setClearPrice(e.target.checked)}
                  data-testid="plan-clear-price"
                />
                {t('plans.clearPrice')}
              </label>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="plan-edit-currency">{t('plans.currency')}</Label>
              <Input
                id="plan-edit-currency"
                value="SAR"
                readOnly
                data-testid="plan-currency-input"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('plans.editEntitlements')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <PlanEntitlementEditor
              catalog={catalog}
              values={entitlements}
              onChange={setEntitlements}
            />
            {inUse ? (
              <div className="space-y-1.5">
                <Label htmlFor="plan-edit-reason">{t('plans.reasonInUse')}</Label>
                <Input
                  id="plan-edit-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={500}
                  placeholder={t('common.reasonPlaceholder')}
                  data-testid="plan-edit-reason"
                />
                <p className="text-xs text-muted-foreground">{t('plans.reasonInUseHint')}</p>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Button type="submit" disabled={updateMutation.isPending} data-testid="plan-save-button">
          {updateMutation.isPending ? t('common.working') : t('plans.save')}
        </Button>
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
        onConfirm={(r) => activateMutation.mutate(r)}
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
        onConfirm={(r) => deactivateMutation.mutate(r)}
        testId="plan-deactivate-dialog"
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:justify-between sm:gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="sm:text-end break-all">{value}</span>
    </div>
  );
}
