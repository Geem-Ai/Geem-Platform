import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  ArrowLeft,
  CircleAlert,
  Coins,
  Layers3,
  Plus,
  RefreshCw,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
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
import { formatMoney } from '@/lib/format';
import { getErrorMessage } from '@/services/api/errors';
import {
  createPlatformPlan,
  fetchEntitlementCatalog,
  platformQueryKeys,
} from '@/services/api/platform';

export function PlanCreatePage() {
  const { t, i18n } = useTranslation();
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
    onError: (error) => toast.error(getErrorMessage(error, t)),
  });

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const catalog = catalogQuery.data?.items ?? [];
    if (catalog.length === 0) {
      toast.error(t('plans.catalogErrorHint'));
      return;
    }
    if (!code.trim() || !name.trim()) {
      toast.error(t('plans.fieldsRequired'));
      return;
    }
    if (!isValidOptionalPrice(priceAmount)) {
      toast.error(t('plans.priceInvalid'));
      return;
    }
    const payload = entitlementDraftToPayload(catalog, entitlements);
    if ('errorKey' in payload) {
      toast.error(t(payload.errorKey));
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

  if (catalogQuery.isLoading) {
    return <PlanCreateSkeleton />;
  }

  if (!catalogQuery.data?.items.length) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8">
        <DocumentTitle title={t('plans.createTitle')} />
        <BackToPlans />
        <Card role="alert" data-testid="plan-create-catalog-error">
          <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 py-12 text-center">
            <span className="mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <CircleAlert className="size-5" aria-hidden />
            </span>
            <h1 className="text-base font-semibold">{t('plans.catalogErrorTitle')}</h1>
            <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
              {catalogQuery.isError
                ? getErrorMessage(catalogQuery.error, t)
                : t('plans.catalogErrorHint')}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-5"
              onClick={() => void catalogQuery.refetch()}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              {t('common.retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const catalog = catalogQuery.data.items;
  const configuredCount = catalog.filter((item) => (entitlements[item.key] ?? '').trim()).length;
  const pending = createMutation.isPending;

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      data-testid="plan-create-page"
    >
      <DocumentTitle title={t('plans.createTitle')} />
      <BackToPlans />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.09] via-background to-background p-5 md:p-7">
        <div className="pointer-events-none absolute -end-20 -top-24 size-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex max-w-3xl items-start gap-4">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-primary/15 bg-background/85 text-primary shadow-xs md:size-14">
            <Plus className="size-6" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              {t('plans.createEyebrow')}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">
              {t('plans.createTitle')}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {t('plans.createHint')}
            </p>
          </div>
        </div>
      </section>

      {catalogQuery.isError ? (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <div className="min-w-0">
            <p className="text-sm font-semibold text-destructive">
              {t('plans.catalogErrorTitle')}
            </p>
            <p className="mt-1 break-words text-xs text-muted-foreground">
              {getErrorMessage(catalogQuery.error, t)}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void catalogQuery.refetch()}
            disabled={catalogQuery.isFetching}
          >
            <RefreshCw className="size-3.5" aria-hidden />
            {t('common.retry')}
          </Button>
        </div>
      ) : null}

      <form
        onSubmit={onSubmit}
        className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]"
        aria-busy={pending}
      >
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader className="items-start py-5 md:px-6">
              <CardHeading>
                <CardTitle>{t('plans.details')}</CardTitle>
                <CardDescription>{t('plans.detailsDescription')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Layers3 className="size-4" aria-hidden />
                </span>
              </CardToolbar>
            </CardHeader>
            <CardContent className="grid gap-5 px-5 py-6 sm:grid-cols-2 md:px-6 md:py-7">
              <div className="space-y-1.5">
                <Label htmlFor="plan-code">{t('plans.code')}</Label>
                <Input
                  id="plan-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  maxLength={64}
                  required
                  dir="ltr"
                  autoCapitalize="none"
                  autoComplete="off"
                  spellCheck={false}
                  disabled={pending}
                  aria-describedby="plan-code-hint"
                  className="font-mono"
                  data-testid="plan-code-input"
                />
                <p id="plan-code-hint" className="text-xs leading-5 text-muted-foreground">
                  {t('plans.codeInputHint')}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-name">{t('plans.name')}</Label>
                <Input
                  id="plan-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  required
                  disabled={pending}
                  data-testid="plan-name-input"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor="plan-description">{t('plans.description')}</Label>
                  <span className="text-[11px] tabular-nums text-muted-foreground">
                    <bdi dir="ltr">{description.length}/2000</bdi>
                  </span>
                </div>
                <textarea
                  id="plan-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  maxLength={2000}
                  rows={4}
                  disabled={pending}
                  className="flex w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="plan-description-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-price">{t('plans.price')}</Label>
                <Input
                  id="plan-price"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  dir="ltr"
                  value={priceAmount}
                  onChange={(event) => setPriceAmount(event.target.value)}
                  placeholder={t('plans.pricePlaceholder')}
                  disabled={pending}
                  aria-describedby="plan-price-hint"
                  className="font-mono tabular-nums"
                  data-testid="plan-price-input"
                />
                <p id="plan-price-hint" className="text-xs leading-5 text-muted-foreground">
                  {t('plans.priceInputHint')}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-currency">{t('plans.currency')}</Label>
                <Input
                  id="plan-currency"
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
                <CardTitle>{t('plans.entitlements')}</CardTitle>
                <CardDescription>{t('plans.entitlementsDescription')}</CardDescription>
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
            <CardContent className="px-5 py-6 md:px-6 md:py-7">
              <PlanEntitlementEditor
                catalog={catalog}
                values={entitlements}
                onChange={setEntitlements}
                disabled={pending}
              />
            </CardContent>
          </Card>
        </div>

        <aside className="min-w-0 xl:sticky xl:top-5">
          <Card data-testid="plan-create-summary">
            <CardHeader className="items-start py-5">
              <CardHeading>
                <CardTitle>{t('plans.reviewTitle')}</CardTitle>
                <CardDescription>{t('plans.reviewDescription')}</CardDescription>
              </CardHeading>
              <CardToolbar>
                <span className="flex size-8 items-center justify-center rounded-lg bg-violet-100 text-violet-700 dark:bg-violet-950/70 dark:text-violet-300">
                  <Sparkles className="size-4" aria-hidden />
                </span>
              </CardToolbar>
            </CardHeader>
            <CardContent className="space-y-5 py-6">
              <div className="rounded-xl border border-primary/15 bg-primary/[0.045] p-4">
                <p className="break-words text-base font-semibold">
                  {name.trim() || t('plans.createTitle')}
                </p>
                <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
                  <bdi dir="ltr">{code.trim() || '—'}</bdi>
                </p>
              </div>
              <SummaryRow
                icon={Coins}
                label={t('plans.price')}
                value={<bdi dir="ltr">{formatMoney(priceAmount.trim() || null, 'SAR')}</bdi>}
              />
              <SummaryRow
                icon={Sparkles}
                label={t('plans.entitlements')}
                value={
                  <bdi dir="ltr" className="tabular-nums">
                    {configuredCount.toLocaleString(i18n.language)} /{' '}
                    {catalog.length.toLocaleString(i18n.language)}
                  </bdi>
                }
              />
            </CardContent>
            <CardFooter className="flex-col items-stretch gap-2 py-4">
              <Button
                type="submit"
                disabled={pending}
                className="w-full"
                data-testid="plan-create-submit"
              >
                <Plus className="size-4" aria-hidden />
                {pending ? t('common.working') : t('plans.create')}
              </Button>
              <Button type="button" variant="outline" asChild className="w-full">
                <Link to="/plans">{t('common.cancel')}</Link>
              </Button>
            </CardFooter>
          </Card>
        </aside>
      </form>
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

function SummaryRow({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 grow">
        <p className="text-xs text-muted-foreground">{label}</p>
        <div className="mt-0.5 break-words text-sm font-semibold">{value}</div>
      </div>
    </div>
  );
}

function PlanCreateSkeleton() {
  const { t } = useTranslation();
  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 p-5 md:p-8"
      aria-busy="true"
      aria-live="polite"
      role="status"
      data-testid="plan-create-loading"
    >
      <span className="sr-only">{t('common.loading')}</span>
      <div className="h-5 w-36 animate-pulse rounded bg-muted" />
      <div className="h-44 animate-pulse rounded-2xl bg-muted" />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <div className="space-y-5">
          <div className="h-96 animate-pulse rounded-xl bg-muted" />
          <div className="h-80 animate-pulse rounded-xl bg-muted" />
        </div>
        <div className="h-80 animate-pulse rounded-xl bg-muted" />
      </div>
    </div>
  );
}

function isValidOptionalPrice(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  const amount = Number(trimmed);
  return Number.isFinite(amount) && amount >= 0;
}
