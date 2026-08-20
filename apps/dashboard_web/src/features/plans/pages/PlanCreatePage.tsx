import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  PlanEntitlementEditor,
  entitlementDraftFromItems,
  entitlementDraftToPayload,
  type EntitlementDraft,
} from '@/features/plans/components/PlanEntitlementEditor';
import { getErrorMessage } from '@/services/api/errors';
import {
  createPlatformPlan,
  fetchEntitlementCatalog,
  platformQueryKeys,
} from '@/services/api/platform';

export function PlanCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [priceAmount, setPriceAmount] = useState('');
  const [entitlements, setEntitlements] = useState<EntitlementDraft>({});

  const catalogQuery = useQuery({
    queryKey: platformQueryKeys.entitlementCatalog,
    queryFn: fetchEntitlementCatalog,
  });

  useEffect(() => {
    if (catalogQuery.data?.items.length && Object.keys(entitlements).length === 0) {
      setEntitlements(entitlementDraftFromItems(catalogQuery.data.items));
    }
  }, [catalogQuery.data, entitlements]);

  const createMutation = useMutation({
    mutationFn: createPlatformPlan,
    onSuccess: async (plan) => {
      await queryClient.invalidateQueries({ queryKey: ['platform', 'plans'] });
      toast.success(t('plans.createSuccess'));
      navigate(`/plans/${plan.id}`);
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const catalog = catalogQuery.data?.items ?? [];
    const payload = entitlementDraftToPayload(catalog, entitlements);
    if ('errorKey' in payload) {
      toast.error(t(payload.errorKey));
      return;
    }
    if (!code.trim() || !name.trim()) {
      toast.error(t('plans.fieldsRequired'));
      return;
    }
    createMutation.mutate({
      code: code.trim(),
      name: name.trim(),
      description: description.trim() || null,
      price_amount: priceAmount.trim() || null,
      currency: 'SAR',
      entitlements: payload,
    });
  };

  return (
    <div className="space-y-4" data-testid="plan-create-page">
      <DocumentTitle title={t('plans.createTitle')} />
      <div className="space-y-2">
        <Link to="/plans" className="text-xs text-muted-foreground hover:underline">
          {t('plans.backToList')}
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">{t('plans.createTitle')}</h1>
        <p className="text-sm text-muted-foreground">{t('plans.createHint')}</p>
      </div>

      {catalogQuery.isLoading ? (
        <div className="h-40 animate-pulse rounded-md bg-muted" />
      ) : catalogQuery.isError ? (
        <p className="text-sm text-destructive">{getErrorMessage(catalogQuery.error, t)}</p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('plans.details')}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="plan-code">{t('plans.code')}</Label>
                <Input
                  id="plan-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  maxLength={64}
                  required
                  data-testid="plan-code-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-name">{t('plans.name')}</Label>
                <Input
                  id="plan-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={200}
                  required
                  data-testid="plan-name-input"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="plan-description">{t('plans.description')}</Label>
                <textarea
                  id="plan-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={2000}
                  rows={3}
                  className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                  data-testid="plan-description-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-price">{t('plans.price')}</Label>
                <Input
                  id="plan-price"
                  value={priceAmount}
                  onChange={(e) => setPriceAmount(e.target.value)}
                  placeholder={t('plans.pricePlaceholder')}
                  data-testid="plan-price-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-currency">{t('plans.currency')}</Label>
                <Input
                  id="plan-currency"
                  value="SAR"
                  readOnly
                  data-testid="plan-currency-input"
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('plans.entitlements')}</CardTitle>
            </CardHeader>
            <CardContent>
              <PlanEntitlementEditor
                catalog={catalogQuery.data?.items ?? []}
                values={entitlements}
                onChange={setEntitlements}
              />
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={createMutation.isPending} data-testid="plan-create-submit">
              {createMutation.isPending ? t('common.working') : t('plans.create')}
            </Button>
            <Button type="button" variant="outline" asChild>
              <Link to="/plans">{t('common.cancel')}</Link>
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
