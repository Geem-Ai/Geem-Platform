import { useMemo } from 'react';
import { Link, useMatch, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Package, RefreshCw, Sparkles } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { canManageWorkspace } from '@/features/workspaces/lib/roles';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { CatalogApp } from '@/services/api/apps';
import { AppGrid } from '../components/AppCard';
import { AppCategoryFilter } from '../components/AppCategoryFilter';
import { AppDetailSheet } from '../components/AppDetailSheet';
import { useAppCategories, useApps } from '../hooks/useAppsQueries';
import { localizeCatalogApp } from '../lib/billing-label';

function AppsSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="apps-loading">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border p-4 space-y-3">
          <div className="flex gap-3">
            <div className="size-10 rounded-xl bg-muted animate-pulse" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/2 rounded bg-muted animate-pulse" />
              <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
            </div>
          </div>
          <div className="h-10 rounded bg-muted animate-pulse" />
        </div>
      ))}
    </div>
  );
}

/**
 * App Store list + Metronic-style floating Sheet for detail / install.
 * `/apps/:slug` opens the sheet without leaving the store page.
 */
export function AppsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { slug } = useParams<{ slug?: string }>();
  const detailMatch = useMatch('/apps/:slug');
  const installedMatch = useMatch('/apps/installed');
  const { currentMembership, currentWorkspace } = useWorkspace();
  const role = currentMembership?.role ?? currentWorkspace?.role;
  const canManage = canManageWorkspace(role);
  const [params, setParams] = useSearchParams();
  const category = params.get('category');

  const sheetOpen =
    Boolean(detailMatch) && !installedMatch && Boolean(slug) && slug !== 'installed';

  const categoriesQuery = useAppCategories();
  const appsQuery = useApps({
    category: category || undefined,
    limit: 50,
    offset: 0,
  });

  const featured = useMemo(
    () => (appsQuery.data?.items ?? []).filter((a) => a.is_featured),
    [appsQuery.data?.items],
  );
  const allApps = appsQuery.data?.items ?? [];
  const activeApp = useMemo(
    () => allApps.find((a) => a.slug === slug) ?? null,
    [allApps, slug],
  );
  const documentTitle = sheetOpen
    ? localizeCatalogApp(
        activeApp ?? {
          slug: slug ?? '',
          name: t('apps.title'),
          short_description: '',
          description: null,
        },
        t,
      ).name
    : t('apps.title');

  const error =
    appsQuery.error instanceof ApiError
      ? t(errorMessageKey(appsQuery.error.code))
      : appsQuery.isError
        ? t('apps.loadError')
        : null;

  function openApp(app: CatalogApp) {
    void navigate(`/apps/${app.slug}`);
  }

  function closeSheet() {
    const next = category ? `?category=${encodeURIComponent(category)}` : '';
    void navigate(`/apps${next}`);
  }

  return (
    <div
      className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-6 ms-auto me-auto"
      data-testid="apps-page"
    >
      <DocumentTitle title={documentTitle} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1 min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('apps.eyebrow')}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">{t('apps.title')}</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            {t('apps.description')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/apps/installed">
              <Package className="size-4" aria-hidden />
              {t('apps.installedApps')}
            </Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void appsQuery.refetch()}
            disabled={appsQuery.isFetching}
          >
            <RefreshCw
              className={`size-4 ${appsQuery.isFetching ? 'animate-spin' : ''}`}
              aria-hidden
            />
            {t('apps.refresh')}
          </Button>
        </div>
      </div>

      <AppCategoryFilter
        categories={categoriesQuery.data ?? []}
        value={category}
        onChange={(nextSlug) => {
          const next = new URLSearchParams(params);
          if (nextSlug) next.set('category', nextSlug);
          else next.delete('category');
          setParams(next, { replace: true });
        }}
      />

      {error ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 space-y-2">
          <p className="text-sm text-destructive">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void appsQuery.refetch()}
          >
            {t('apps.retry')}
          </Button>
        </div>
      ) : null}

      {appsQuery.isLoading ? <AppsSkeleton /> : null}

      {!appsQuery.isLoading && !error ? (
        <div className="space-y-5">
          {!category && featured.length > 0 ? (
            <section className="space-y-2.5" data-testid="apps-featured">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-muted-foreground" aria-hidden />
                <h2 className="text-sm font-semibold tracking-tight">
                  {t('apps.featured')}
                </h2>
              </div>
              <AppGrid
                apps={featured}
                emptyLabel={t('apps.empty')}
                onOpen={openApp}
              />
            </section>
          ) : null}

          <section className="space-y-2.5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold tracking-tight">
                {t('apps.allApps')}
              </h2>
              {!canManage ? (
                <p className="text-xs text-muted-foreground">{t('apps.memberHint')}</p>
              ) : null}
            </div>
            <AppGrid apps={allApps} emptyLabel={t('apps.empty')} onOpen={openApp} />
          </section>
        </div>
      ) : null}

      <AppDetailSheet
        slug={sheetOpen ? slug : undefined}
        open={sheetOpen}
        onOpenChange={(open) => {
          if (!open) closeSheet();
        }}
      />
    </div>
  );
}
