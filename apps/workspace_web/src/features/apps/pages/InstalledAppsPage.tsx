import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, RefreshCw, Store } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { usePermissions } from '@/features/authz/usePermissions';
import { WorkspacePermission } from '@/features/authz/permissions';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { InstalledAppCard } from '../components/InstalledAppCard';
import { useAppInstallations } from '../hooks/useAppsQueries';

export function InstalledAppsPage() {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canManage = can(WorkspacePermission.APPS_MANAGE);
  const query = useAppInstallations();

  const error =
    query.error instanceof ApiError
      ? t(errorMessageKey(query.error.code))
      : query.isError
        ? t('apps.loadError')
        : null;

  return (
    <div
      className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-6 ms-auto me-auto"
      data-testid="installed-apps-page"
    >
      <DocumentTitle title={t('apps.installedApps')} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <Button asChild variant="ghost" size="sm" className="-ms-2 mb-1">
            <Link to="/apps">
              <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden />
              {t('apps.backToStore')}
            </Link>
          </Button>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t('apps.installedApps')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            {t('apps.installedDescription')}
          </p>
          {!canManage ? (
            <p className="text-sm text-muted-foreground" data-testid="installed-member-hint">
              {t('apps.memberHint')}
            </p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          <RefreshCw
            className={`size-4 ${query.isFetching ? 'animate-spin' : ''}`}
            aria-hidden
          />
          {t('apps.refresh')}
        </Button>
      </div>

      {error ? (
        <Card className="shadow-xs border-destructive/30">
          <CardContent className="p-6 space-y-3">
            <p className="text-sm text-destructive">{error}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void query.refetch()}
            >
              {t('apps.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {query.isLoading ? (
        <div className="space-y-3" data-testid="installed-loading">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-28 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : null}

      {!query.isLoading && !error && (query.data?.items.length ?? 0) === 0 ? (
        <Card className="shadow-xs" data-testid="installed-empty">
          <CardContent className="p-10 flex flex-col items-center text-center gap-3">
            <Store className="size-8 text-muted-foreground" aria-hidden />
            <h2 className="text-base font-semibold">{t('apps.installedEmptyTitle')}</h2>
            <p className="text-sm text-muted-foreground max-w-md">
              {t('apps.installedEmptyHint')}
            </p>
            <Button asChild>
              <Link to="/apps">{t('apps.browseStore')}</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!query.isLoading && !error && (query.data?.items.length ?? 0) > 0 ? (
        <div className="space-y-3">
          {query.data!.items.map((item) => (
            <InstalledAppCard
              key={item.id}
              installation={item}
              canManage={canManage}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
