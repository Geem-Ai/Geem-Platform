import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { invalidateAppsCache } from '@/features/apps/hooks/useAppsQueries';
import type { Expert } from '@/services/api/types';
import type { WhatsAppConnection } from '@/services/api/apps';
import { reconnectWhatsApp, updateChannelSettings } from '@/services/api/apps';
import {
  ApiError,
  errorMessageKey,
  friendlyDisplayError,
} from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';
import { useDisconnectConnection } from '../../connections/hooks/useConnectionQueries';
import { isConnectingStatus } from '../lib';
import { WhatsAppStatusBadge } from './WhatsAppStatusBadge';

function titleFor(connection: WhatsAppConnection, t: (key: string) => string): string {
  return (
    connection.display_name ||
    connection.external_account_name ||
    connection.phone ||
    t('apps.connections.untitled')
  );
}

export function WhatsAppConnectionCard({
  connection,
  canManage,
  onResumeConnect,
}: {
  connection: WhatsAppConnection;
  canManage: boolean;
  onResumeConnect?: (connection: WhatsAppConnection) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const expertsQuery = useExperts();
  const disconnect = useDisconnectConnection();
  const [expertId, setExpertId] = useState(connection.expert_id ?? '');
  const [enabled, setEnabled] = useState(Boolean(connection.enabled ?? true));
  const [autoReplyEnabled, setAutoReplyEnabled] = useState(
    Boolean(connection.auto_reply_enabled ?? true),
  );
  const [respondToGroups, setRespondToGroups] = useState(
    Boolean(connection.respond_to_groups ?? false),
  );

  useEffect(() => {
    setExpertId(connection.expert_id ?? '');
    setEnabled(Boolean(connection.enabled ?? true));
    setAutoReplyEnabled(Boolean(connection.auto_reply_enabled ?? true));
    setRespondToGroups(Boolean(connection.respond_to_groups ?? false));
  }, [
    connection.auto_reply_enabled,
    connection.enabled,
    connection.expert_id,
    connection.respond_to_groups,
  ]);

  const experts = useMemo(() => {
    const rows = expertsQuery.data ?? [];
    return rows.filter((expert) => expert.status === 'ready');
  }, [expertsQuery.data]);

  const selectedExpertExists = experts.some((expert) => expert.id === expertId);
  const reconnectMutation = useMutation({
    mutationFn: () => reconnectWhatsApp(connection.app_slug, connection.id),
    onSuccess: async (result) => {
      toast.success(t('apps.whatsapp.toasts.reconnecting'));
      await Promise.all([
        invalidateAppsCache(queryClient, workspaceId, connection.app_slug),
        queryClient.invalidateQueries({
          queryKey: queryKeys.appConnections(workspaceId, connection.app_slug),
        }),
      ]);
      if (onResumeConnect && isConnectingStatus(result)) {
        onResumeConnect(result);
      }
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      updateChannelSettings(connection.app_slug, connection.id, {
        expert_id: expertId || null,
        enabled,
        auto_reply_enabled: autoReplyEnabled,
        respond_to_groups: respondToGroups,
      }),
    onSuccess: async () => {
      toast.success(t('apps.whatsapp.toasts.settingsSaved'));
      await Promise.all([
        invalidateAppsCache(queryClient, workspaceId, connection.app_slug),
        queryClient.invalidateQueries({
          queryKey: queryKeys.appConnections(workspaceId, connection.app_slug),
        }),
      ]);
    },
  });

  const dirty =
    expertId !== (connection.expert_id ?? '') ||
    enabled !== Boolean(connection.enabled ?? true) ||
    autoReplyEnabled !== Boolean(connection.auto_reply_enabled ?? true) ||
    respondToGroups !== Boolean(connection.respond_to_groups ?? false);

  const actionError =
    reconnectMutation.error instanceof ApiError
      ? errorMessageKey(reconnectMutation.error.code)
      : updateMutation.error instanceof ApiError
        ? errorMessageKey(updateMutation.error.code)
        : disconnect.error instanceof ApiError
          ? errorMessageKey(disconnect.error.code)
          : null;

  return (
    <div
      className="rounded-xl border border-border px-4 py-4 space-y-4"
      data-testid={`whatsapp-connection-card-${connection.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium">{titleFor(connection, t)}</p>
        <WhatsAppStatusBadge connection={connection} />
      </div>

      <div className="space-y-1 text-sm text-muted-foreground">
        {connection.phone ? (
          <p data-testid="whatsapp-connection-phone">
            {t('apps.whatsapp.connection.phone', { phone: connection.phone })}
          </p>
        ) : null}
        <p>
          {t('apps.whatsapp.connection.providerStatus', {
            status: connection.provider_status || t('apps.whatsapp.status.connecting'),
          })}
        </p>
      </div>

      {connection.last_error_code || connection.last_error_message ? (
        <p className="text-sm text-destructive">
          {friendlyDisplayError(t, {
            code: connection.last_error_code,
            message: connection.last_error_message,
          })}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1.5 text-sm">
          <span className="font-medium">{t('apps.whatsapp.connection.expert')}</span>
          <select
            className="w-full rounded-md border border-border bg-background px-3 py-2"
            value={expertId}
            onChange={(event) => setExpertId(event.target.value)}
            disabled={!canManage || expertsQuery.isLoading}
            data-testid="whatsapp-expert-select"
          >
            <option value="">{t('apps.whatsapp.connection.unassignedExpert')}</option>
            {!selectedExpertExists && connection.expert_id ? (
              <option value={connection.expert_id}>{connection.expert_id}</option>
            ) : null}
            {experts.map((expert: Expert) => (
              <option key={expert.id} value={expert.id}>
                {expert.name}
              </option>
            ))}
          </select>
        </label>

        <div className="space-y-2 text-sm">
          <p className="font-medium">{t('apps.whatsapp.connection.settings')}</p>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
              disabled={!canManage}
              data-testid="whatsapp-enabled"
            />
            <span>{t('apps.whatsapp.connection.enabled')}</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoReplyEnabled}
              onChange={(event) => setAutoReplyEnabled(event.target.checked)}
              disabled={!canManage}
              data-testid="whatsapp-auto-reply"
            />
            <span>{t('apps.whatsapp.connection.autoReply')}</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={respondToGroups}
              onChange={(event) => setRespondToGroups(event.target.checked)}
              disabled={!canManage}
              data-testid="whatsapp-respond-to-groups"
            />
            <span>{t('apps.whatsapp.connection.respondToGroups')}</span>
          </label>
        </div>
      </div>

      {!canManage ? (
        <p className="text-sm text-muted-foreground" data-testid="whatsapp-member-readonly">
          {t('apps.whatsapp.connection.readOnly')}
        </p>
      ) : null}

      {actionError ? <p className="text-sm text-destructive">{t(actionError)}</p> : null}

      {canManage ? (
        <div className="flex flex-wrap gap-2">
          {isConnectingStatus(connection) && onResumeConnect ? (
            <Button
              size="sm"
              onClick={() => onResumeConnect(connection)}
              data-testid="whatsapp-resume-connect"
            >
              {t('apps.whatsapp.connect.resume')}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => updateMutation.mutate()}
            disabled={!dirty || updateMutation.isPending}
            data-testid="whatsapp-save-settings"
          >
            {t('common.save')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => reconnectMutation.mutate()}
            disabled={reconnectMutation.isPending || isConnectingStatus(connection)}
            data-testid="whatsapp-reconnect"
          >
            {t('apps.connections.reconnect')}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() =>
              disconnect.mutate({
                slug: connection.app_slug,
                connectionId: connection.id,
              })
            }
            disabled={disconnect.isPending}
            data-testid="whatsapp-disconnect"
          >
            {t('apps.connections.disconnect')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
