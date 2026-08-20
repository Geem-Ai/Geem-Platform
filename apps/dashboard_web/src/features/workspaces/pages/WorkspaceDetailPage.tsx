import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import {
  UserStatusBadge,
  WorkspaceKindBadge,
  WorkspaceStatusBadge,
} from '@/components/shared/StatusBadges';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate, formatAdminDateTime, formatBytes } from '@/lib/dates';
import { getErrorMessage } from '@/services/api/errors';
import {
  disablePlatformWorkspace,
  enablePlatformWorkspace,
  fetchPlatformWorkspace,
  fetchPlatformWorkspaceMembers,
  platformQueryKeys,
} from '@/services/api/platform';

export function WorkspaceDetailPage() {
  const { workspaceId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<'disable' | 'enable' | null>(null);

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.workspace(workspaceId),
    queryFn: () => fetchPlatformWorkspace(workspaceId),
    enabled: Boolean(workspaceId),
  });

  const membersQuery = useQuery({
    queryKey: platformQueryKeys.workspaceMembers(workspaceId, { limit: 50, offset: 0 }),
    queryFn: () => fetchPlatformWorkspaceMembers(workspaceId, { limit: 50, offset: 0 }),
    enabled: Boolean(workspaceId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'workspaces'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.workspace(workspaceId) });
    await queryClient.invalidateQueries({
      queryKey: ['platform', 'workspace', workspaceId, 'members'],
    });
  };

  const disableMutation = useMutation({
    mutationFn: (reason: string) => disablePlatformWorkspace(workspaceId, reason),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('workspaces.disableSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const enableMutation = useMutation({
    mutationFn: (reason: string) => enablePlatformWorkspace(workspaceId, reason || undefined),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('workspaces.enableSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-3" data-testid="workspace-detail-loading">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-40 animate-pulse rounded-md bg-muted" />
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <p className="text-sm text-destructive" data-testid="workspace-detail-error">
        {getErrorMessage(detailQuery.error, t)}
      </p>
    );
  }

  const ws = detailQuery.data;
  const isSystem = ws.kind === 'system';
  const isSuspended = ws.status === 'suspended';
  const isActive = ws.status === 'active';

  return (
    <div className="space-y-4" data-testid="workspace-detail-page">
      <DocumentTitle title={ws.name} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <Link to="/workspaces" className="text-xs text-muted-foreground hover:underline">
            {t('workspaces.backToList')}
          </Link>
          <h1 className="text-xl font-semibold tracking-tight truncate">{ws.name}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{ws.slug}</span>
            <WorkspaceStatusBadge status={ws.status} />
            <WorkspaceKindBadge kind={ws.kind} />
          </div>
        </div>
        {!isSystem && isActive ? (
          <Button
            variant="destructive"
            onClick={() => setDialog('disable')}
            data-testid="workspace-disable-button"
          >
            {t('workspaces.disable')}
          </Button>
        ) : null}
        {!isSystem && isSuspended ? (
          <Button onClick={() => setDialog('enable')} data-testid="workspace-enable-button">
            {t('workspaces.enable')}
          </Button>
        ) : null}
        {isSystem ? (
          <p className="text-xs text-muted-foreground max-w-xs" data-testid="workspace-system-protected">
            {t('workspaces.systemProtected')}
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('workspaces.overview')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label={t('workspaces.created')} value={formatAdminDateTime(ws.created_at, i18n.language)} />
            <Row label={t('workspaces.members')} value={String(ws.members_count)} />
            <Row
              label={t('workspaces.owners')}
              value={
                ws.owners.length
                  ? ws.owners.map((o) => o.email).join(', ')
                  : t('common.none')
              }
            />
            {ws.subscription ? (
              <>
                <Row label={t('workspaces.plan')} value={ws.subscription.plan_name} />
                <Row label={t('workspaces.subscriptionStatus')} value={ws.subscription.status} />
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('workspaces.resources')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label={t('workspaces.experts')} value={String(ws.resources.experts_count)} />
            <Row label={t('workspaces.apiKeys')} value={String(ws.resources.api_keys_count)} />
            <Row
              label={t('workspaces.appInstallations')}
              value={String(ws.resources.app_installations_count)}
            />
            <Row
              label={t('workspaces.storage')}
              value={
                ws.resources.storage_used_bytes != null
                  ? `${formatBytes(ws.resources.storage_used_bytes, i18n.language)} / ${formatBytes(ws.resources.storage_limit_bytes, i18n.language)}`
                  : '—'
              }
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('workspaces.membersSection')}</CardTitle>
        </CardHeader>
        <CardContent>
          {membersQuery.isLoading ? (
            <div className="h-20 animate-pulse rounded bg-muted" />
          ) : membersQuery.isError ? (
            <p className="text-sm text-destructive">{getErrorMessage(membersQuery.error, t)}</p>
          ) : membersQuery.data?.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('workspaces.noMembers')}</p>
          ) : (
            <ul className="divide-y divide-border" data-testid="workspace-members-list">
              {membersQuery.data?.items.map((m) => (
                <li
                  key={m.membership_id}
                  className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
                  data-testid="workspace-member-row"
                >
                  <div className="min-w-0">
                    <Link
                      to={`/users/${m.user_id}`}
                      className="text-sm font-medium hover:underline truncate block"
                    >
                      {m.email}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {m.role_name}
                      {m.is_owner_role ? ` · ${t('workspaces.ownerRole')}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <UserStatusBadge status={m.user_status} />
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatAdminDate(m.created_at, i18n.language)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <LifecycleDialog
        open={dialog === 'disable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('workspaces.disableTitle')}
        description={t('workspaces.disableHint')}
        reasonRequired
        confirmLabel={t('workspaces.disable')}
        pending={disableMutation.isPending}
        onConfirm={(reason) => disableMutation.mutate(reason)}
        testId="workspace-disable-dialog"
      />
      <LifecycleDialog
        open={dialog === 'enable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('workspaces.enableTitle')}
        description={t('workspaces.enableHint')}
        reasonRequired={false}
        confirmLabel={t('workspaces.enable')}
        confirmVariant="primary"
        pending={enableMutation.isPending}
        onConfirm={(reason) => enableMutation.mutate(reason)}
        testId="workspace-enable-dialog"
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
