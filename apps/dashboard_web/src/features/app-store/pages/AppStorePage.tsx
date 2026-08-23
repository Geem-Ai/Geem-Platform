import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  AppWindow,
  ChevronRight,
  Plus,
  RefreshCw,
  SearchX,
} from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminFilterMenu } from '@/components/shared/AdminFilterMenu';
import { AdminPagination } from '@/components/shared/AdminPagination';
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
import { formatAdminDate } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformAppCategories,
  fetchPlatformApps,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformAppListItem } from '@/services/api/types';

const PAGE_SIZE = 25;

export function AppStorePage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [billingType, setBillingType] = useState('');
  const [category, setCategory] = useState('');
  const [connectorKind, setConnectorKind] = useState('');
  const [offset, setOffset] = useState(0);

  const categoriesQuery = useQuery({
    queryKey: platformQueryKeys.appCategories,
    queryFn: fetchPlatformAppCategories,
  });

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      billing_type: billingType || undefined,
      category: category || undefined,
      connector_kind: connectorKind || undefined,
    }),
    [billingType, category, connectorKind, offset, search, status],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.apps(filters),
    queryFn: () => fetchPlatformApps(filters),
  });

  const categoryOptions = useMemo(
    () =>
      (categoriesQuery.data?.items ?? [])
        .filter((item) => item.is_active)
        .map((item) => ({
          value: item.slug,
          labelKey: `appStore.categories.${item.slug}`,
        })),
    [categoriesQuery.data],
  );

  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setBillingType('');
    setCategory('');
    setConnectorKind('');
    setOffset(0);
  };

  return (
    <div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 p-5 md:p-8"
      data-testid="app-store-page"
    >
      <DocumentTitle title={t('appStore.title')} />

      <section className="relative overflow-hidden rounded-2xl border border-border bg-linear-to-br from-primary/[0.08] via-background to-background p-5 md:p-7">
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary rtl:tracking-normal">
              <AppWindow className="size-3.5" aria-hidden />
              {t('appStore.eyebrow')}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
              {t('appStore.title')}
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t('appStore.subtitle')}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              data-testid="app-store-refresh"
            >
              <RefreshCw className={cn('size-4', query.isFetching && 'animate-spin')} aria-hidden />
              {t('common.refresh')}
            </Button>
            <Button asChild data-testid="app-store-create-button">
              <Link to="/app-store/new">
                <Plus className="size-4" aria-hidden />
                {t('appStore.create')}
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardHeading>
            <CardTitle>{t('appStore.inventoryTitle')}</CardTitle>
            <CardDescription>{t('appStore.inventorySubtitle')}</CardDescription>
          </CardHeading>
          <CardToolbar>
            <AdminFilterMenu
              search={search}
              onSearchChange={(value) => {
                setSearch(value);
                setOffset(0);
              }}
              searchPlaceholderKey="appStore.searchPlaceholder"
              fields={[
                {
                  id: 'status',
                  labelKey: 'common.status',
                  value: status,
                  onChange: (value) => {
                    setStatus(value);
                    setOffset(0);
                  },
                  options: [
                    { value: 'draft', labelKey: 'appStore.status.draft' },
                    { value: 'published', labelKey: 'appStore.status.published' },
                    { value: 'coming_soon', labelKey: 'appStore.status.coming_soon' },
                    { value: 'disabled', labelKey: 'appStore.status.disabled' },
                  ],
                },
                {
                  id: 'billing_type',
                  labelKey: 'appStore.filters.billingType',
                  value: billingType,
                  onChange: (value) => {
                    setBillingType(value);
                    setOffset(0);
                  },
                  options: [
                    { value: 'free', labelKey: 'appStore.billingType.free' },
                    { value: 'one_time', labelKey: 'appStore.billingType.one_time' },
                    { value: 'subscription', labelKey: 'appStore.billingType.subscription' },
                  ],
                },
                {
                  id: 'category',
                  labelKey: 'appStore.filters.category',
                  value: category,
                  onChange: (value) => {
                    setCategory(value);
                    setOffset(0);
                  },
                  options: categoryOptions,
                },
                {
                  id: 'connector_kind',
                  labelKey: 'appStore.filters.connectorKind',
                  value: connectorKind,
                  onChange: (value) => {
                    setConnectorKind(value);
                    setOffset(0);
                  },
                  options: [
                    { value: 'connector', labelKey: 'appStore.connectorKind.connector' },
                    { value: 'widget', labelKey: 'appStore.connectorKind.widget' },
                  ],
                },
              ]}
              onReset={resetFilters}
              testIdPrefix="app-store"
            />
          </CardToolbar>
        </CardHeader>
        <CardContent className="space-y-4">
          {query.isError ? (
            <p className="text-sm text-destructive" data-testid="app-store-error">
              {getErrorMessage(query.error, t)}
            </p>
          ) : null}

          {query.isLoading ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : null}

          {query.data && query.data.items.length === 0 ? (
            <div
              className="flex flex-col items-center gap-3 py-12 text-center"
              data-testid="app-store-empty"
            >
              <SearchX className="size-10 text-muted-foreground/60" aria-hidden />
              <p className="text-sm text-muted-foreground">{t('appStore.empty')}</p>
            </div>
          ) : null}

          {query.data?.items.map((app) => (
            <AppRow key={app.id} app={app} locale={i18n.language} />
          ))}

          {query.data ? (
            <AdminPagination
              total={query.data.total}
              limit={query.data.limit}
              offset={query.data.offset}
              onPageChange={setOffset}
              testId="app-store-pagination"
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function AppRow({ app, locale }: { app: PlatformAppListItem; locale: string }) {
  const { t } = useTranslation();

  return (
    <Link
      to={`/app-store/${app.id}`}
      className="flex flex-col gap-3 rounded-xl border border-border p-4 transition-colors hover:bg-muted/30 md:flex-row md:items-center md:justify-between"
      data-testid={`app-store-row-${app.id}`}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{app.name}</span>
          <Badge variant="secondary" appearance="light" size="sm">
            {t(`appStore.status.${app.status}`, { defaultValue: app.status })}
          </Badge>
          <Badge variant="info" appearance="light" size="sm">
            {t(`appStore.billingType.${app.billing_type}`, { defaultValue: app.billing_type })}
          </Badge>
        </div>
        <p className="line-clamp-2 text-sm text-muted-foreground">{app.short_description}</p>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span className="font-mono">{app.slug}</span>
          <span>{app.category_slug}</span>
          <span>{t('appStore.plansCount', { count: app.plans_count })}</span>
          <span>{t('appStore.installationsCount', { count: app.installations_count })}</span>
          <span>{formatAdminDate(app.updated_at, locale)}</span>
        </div>
      </div>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground rtl:rotate-180" aria-hidden />
    </Link>
  );
}
