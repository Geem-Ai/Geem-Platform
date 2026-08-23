import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { AppWindow, ArrowUpRight, CircleAlert, RefreshCw } from 'lucide-react';
import { GrantAppDialog } from '@/features/app-store/components/GrantAppDialog';
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
import { formatAdminDateTime } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformApp,
  fetchPlatformWorkspaceApps,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformWorkspaceApp } from '@/services/api/types';

type WorkspaceAppsSectionProps = {
  workspaceId: string;
  workspaceName: string;
  isSystem: boolean;
};

export function WorkspaceAppsSection({
  workspaceId,
  workspaceName,
  isSystem,
}: WorkspaceAppsSectionProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [dialogApp, setDialogApp] = useState<PlatformWorkspaceApp | null>(null);
  const [dialogMode, setDialogMode] = useState<'grant' | 'revoke' | 'extend'>('grant');

  const appsQuery = useQuery({
    queryKey: platformQueryKeys.workspaceApps(workspaceId),
    queryFn: () => fetchPlatformWorkspaceApps(workspaceId),
    enabled: Boolean(workspaceId) && !isSystem,
    retry: false,
  });

  const detailAppId = dialogApp?.app_id ?? '';
  const appDetailQuery = useQuery({
    queryKey: platformQueryKeys.app(detailAppId),
    queryFn: () => fetchPlatformApp(detailAppId),
    enabled: Boolean(detailAppId),
  });

  const plans = useMemo(() => appDetailQuery.data?.plans ?? [], [appDetailQuery.data?.plans]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({
      queryKey: platformQueryKeys.workspaceApps(workspaceId),
    });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.workspace(workspaceId) });
  };

  if (isSystem) {
    return (
      <Card data-testid="workspace-apps-section">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          {t('appStore.systemWorkspaceHint')}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="workspace-apps-section">
      <CardHeader>
        <CardHeading>
          <CardTitle>{t('appStore.workspaceSectionTitle')}</CardTitle>
          <CardDescription>{t('appStore.workspaceSectionSubtitle')}</CardDescription>
        </CardHeading>
        <CardToolbar>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void appsQuery.refetch()}
            disabled={appsQuery.isFetching}
            data-testid="workspace-apps-refresh"
          >
            <RefreshCw className={cn('size-3.5', appsQuery.isFetching && 'animate-spin')} aria-hidden />
            {t('common.refresh')}
          </Button>
        </CardToolbar>
      </CardHeader>
      <CardContent className="space-y-3">
        {appsQuery.isError ? (
          <p className="text-sm text-destructive" data-testid="workspace-apps-error">
            {getErrorMessage(appsQuery.error, t)}
          </p>
        ) : null}

        {appsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : null}

        {appsQuery.data?.items && appsQuery.data.items.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground" data-testid="workspace-apps-empty">
            {t('appStore.workspaceAppsEmpty')}
          </p>
        ) : null}

        {(appsQuery.data?.items ?? []).map((app) => (
          <WorkspaceAppRow
            key={app.app_id}
            app={app}
            locale={i18n.language}
            onGrant={() => {
              setDialogApp(app);
              setDialogMode('grant');
            }}
            onExtend={() => {
              setDialogApp(app);
              setDialogMode('extend');
            }}
            onRevoke={() => {
              setDialogApp(app);
              setDialogMode('revoke');
            }}
          />
        ))}
      </CardContent>

      <GrantAppDialog
        open={Boolean(dialogApp)}
        onOpenChange={(open) => !open && setDialogApp(null)}
        workspaceId={workspaceId}
        workspaceName={workspaceName}
        app={dialogApp}
        plans={plans}
        mode={dialogMode}
        onComplete={() => void invalidate()}
      />
    </Card>
  );
}

function WorkspaceAppRow({
  app,
  locale,
  onGrant,
  onExtend,
  onRevoke,
}: {
  app: PlatformWorkspaceApp;
  locale: string;
  onGrant: () => void;
  onExtend: () => void;
  onRevoke: () => void;
}) {
  const { t } = useTranslation();
  const canGrant =
    app.billing_type !== 'free' &&
    (app.access_status === 'not_entitled' || app.access_status === 'expired');
  const canExtend =
    app.billing_type === 'subscription' &&
    app.subscription_status === 'active' &&
    app.access_status === 'active';
  const canRevoke =
    app.billing_type === 'one_time'
      ? app.license_status === 'active'
      : app.billing_type === 'subscription'
        ? app.subscription_status === 'active'
        : false;

  return (
    <div
      className="flex flex-col gap-3 rounded-xl border border-border p-4 md:flex-row md:items-center md:justify-between"
      data-testid={`workspace-app-row-${app.app_id}`}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <AppWindow className="size-4 text-primary" aria-hidden />
          <span className="font-medium">{app.app_name}</span>
          <Badge variant="secondary" appearance="light" size="sm">
            {t(`appStore.billingType.${app.billing_type}`, { defaultValue: app.billing_type })}
          </Badge>
          <Badge variant="info" appearance="light" size="sm">
            {t(`appStore.catalogStatus.${app.catalog_status}`, { defaultValue: app.catalog_status })}
          </Badge>
          <Badge
            variant={app.access_status === 'active' ? 'success' : 'secondary'}
            appearance="light"
            size="sm"
          >
            {t(`appStore.accessStatus.${app.access_status}`, { defaultValue: app.access_status })}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {app.plan_name ? <span>{t('appStore.currentPlan', { plan: app.plan_name })}</span> : null}
          {app.current_period_end ? (
            <span>
              {t('appStore.periodEnd', {
                date: formatAdminDateTime(app.current_period_end, locale),
              })}
            </span>
          ) : null}
          {app.installed ? (
            <span>{t('appStore.installed')}</span>
          ) : (
            <span>{t('appStore.notInstalled')}</span>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {canGrant ? (
          <Button size="sm" onClick={onGrant} data-testid={`workspace-app-grant-${app.app_id}`}>
            {t('appStore.grant')}
          </Button>
        ) : null}
        {canExtend ? (
          <Button
            size="sm"
            variant="outline"
            onClick={onExtend}
            data-testid={`workspace-app-extend-${app.app_id}`}
          >
            {t('appStore.extend')}
          </Button>
        ) : null}
        {canRevoke ? (
          <Button
            size="sm"
            variant="destructive"
            onClick={onRevoke}
            data-testid={`workspace-app-revoke-${app.app_id}`}
          >
            {t('appStore.revoke')}
          </Button>
        ) : null}
        <Button size="sm" variant="outline" asChild>
          <Link to={`/app-store/${app.app_id}`}>
            {t('appStore.viewApp')}
            <ArrowUpRight className="size-3.5 rtl:-scale-x-100" aria-hidden />
          </Link>
        </Button>
      </div>
    </div>
  );
}
