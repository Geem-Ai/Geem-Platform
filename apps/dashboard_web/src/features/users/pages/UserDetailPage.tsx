import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { LifecycleDialog } from '@/components/shared/LifecycleDialog';
import {
  PlatformRoleBadge,
  UserStatusBadge,
  WorkspaceStatusBadge,
} from '@/components/shared/StatusBadges';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDateTime } from '@/lib/dates';
import { useAuth } from '@/features/auth/AuthProvider';
import { getErrorMessage } from '@/services/api/errors';
import {
  disablePlatformUser,
  enablePlatformUser,
  fetchPlatformUser,
  platformQueryKeys,
} from '@/services/api/platform';

export function UserDetailPage() {
  const { userId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<'disable' | 'enable' | null>(null);

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.user(userId),
    queryFn: () => fetchPlatformUser(userId),
    enabled: Boolean(userId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['platform', 'users'] });
    await queryClient.invalidateQueries({ queryKey: platformQueryKeys.user(userId) });
  };

  const disableMutation = useMutation({
    mutationFn: (reason: string) => disablePlatformUser(userId, reason),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('users.disableSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  const enableMutation = useMutation({
    mutationFn: (reason: string) => enablePlatformUser(userId, reason || undefined),
    onSuccess: async () => {
      await invalidate();
      setDialog(null);
      toast.success(t('users.enableSuccess'));
    },
    onError: (err) => toast.error(getErrorMessage(err, t)),
  });

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-3" data-testid="user-detail-loading">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-40 animate-pulse rounded-md bg-muted" />
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <p className="text-sm text-destructive" data-testid="user-detail-error">
        {getErrorMessage(detailQuery.error, t)}
      </p>
    );
  }

  const u = detailQuery.data;
  const isSelf = me?.id === u.id;
  const isActive = u.status === 'active';
  const isDisabled = u.status === 'disabled';

  return (
    <div className="space-y-4" data-testid="user-detail-page">
      <DocumentTitle title={u.email} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <Link to="/users" className="text-xs text-muted-foreground hover:underline">
            {t('users.backToList')}
          </Link>
          <h1 className="text-xl font-semibold tracking-tight truncate">{u.email}</h1>
          <div className="flex flex-wrap items-center gap-2">
            <UserStatusBadge status={u.status} />
            <PlatformRoleBadge role={u.platform_role} />
          </div>
        </div>
        {!isSelf && isActive ? (
          <Button
            variant="destructive"
            onClick={() => setDialog('disable')}
            data-testid="user-disable-button"
          >
            {t('users.disable')}
          </Button>
        ) : null}
        {!isSelf && isDisabled ? (
          <Button onClick={() => setDialog('enable')} data-testid="user-enable-button">
            {t('users.enable')}
          </Button>
        ) : null}
        {isSelf ? (
          <p className="text-xs text-muted-foreground" data-testid="user-self-protected">
            {t('users.selfProtected')}
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('users.profile')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label={t('users.created')} value={formatAdminDateTime(u.created_at, i18n.language)} />
            <Row
              label={t('users.emailVerified')}
              value={
                u.email_verified_at
                  ? formatAdminDateTime(u.email_verified_at, i18n.language)
                  : t('users.unverified')
              }
            />
            <Row
              label={t('users.lastLogin')}
              value={formatAdminDateTime(u.last_login_at, i18n.language)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('users.security')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label={t('users.status')} value={t(`status.user.${u.status}`)} />
            <Row
              label={t('users.platformRole')}
              value={t(`status.platformRole.${u.platform_role}`)}
            />
            <Row label={t('users.activeSessions')} value={String(u.active_session_count)} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('users.workspacesSection')}</CardTitle>
        </CardHeader>
        <CardContent>
          {u.memberships.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('users.noWorkspaces')}</p>
          ) : (
            <ul className="divide-y divide-border" data-testid="user-memberships-list">
              {u.memberships.map((m) => (
                <li
                  key={m.membership_id}
                  className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
                  data-testid="user-membership-row"
                >
                  <div className="min-w-0">
                    <Link
                      to={`/workspaces/${m.workspace_id}`}
                      className="text-sm font-medium hover:underline truncate block"
                    >
                      {m.workspace_name}
                    </Link>
                    <p className="text-xs text-muted-foreground font-mono">{m.workspace_slug}</p>
                    <p className="text-xs text-muted-foreground">
                      {m.role_name}
                      {m.is_owner_role ? ` · ${t('workspaces.ownerRole')}` : ''}
                    </p>
                  </div>
                  <WorkspaceStatusBadge status={m.workspace_status} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <LifecycleDialog
        open={dialog === 'disable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('users.disableTitle')}
        description={t('users.disableHint')}
        reasonRequired
        confirmLabel={t('users.disable')}
        pending={disableMutation.isPending}
        onConfirm={(reason) => disableMutation.mutate(reason)}
        testId="user-disable-dialog"
      />
      <LifecycleDialog
        open={dialog === 'enable'}
        onOpenChange={(open) => !open && setDialog(null)}
        title={t('users.enableTitle')}
        description={t('users.enableHint')}
        reasonRequired={false}
        confirmLabel={t('users.enable')}
        confirmVariant="primary"
        pending={enableMutation.isPending}
        onConfirm={(reason) => enableMutation.mutate(reason)}
        testId="user-enable-dialog"
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
