import { useEffect, useId, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { inputVariants } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { AppIcon } from '@/features/apps/components/AppIcon';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { invalidateAppsCache } from '@/features/apps/hooks/useAppsQueries';
import { cn } from '@/lib/utils';
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
import {
  isConnectingStatus,
  resolveWhatsAppUiStatus,
  whatsappPhoneLabel,
  type WhatsAppUiStatusKey,
} from '../lib';
import { WhatsAppStatusBadge } from './WhatsAppStatusBadge';

function titleFor(connection: WhatsAppConnection, t: (key: string) => string): string {
  return (
    connection.display_name ||
    connection.external_account_name ||
    connection.phone ||
    t('apps.connections.untitled')
  );
}

function ChannelToggle({
  checked,
  onCheckedChange,
  disabled,
  label,
  description,
  testId,
}: {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  disabled?: boolean;
  label: string;
  description: string;
  testId: string;
}) {
  return (
    <label
      className={cn(
        'flex items-start justify-between gap-4 py-3.5',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
      )}
    >
      <span className="min-w-0 space-y-1">
        <span className="block text-sm font-medium leading-none">{label}</span>
        <span className="block text-xs text-muted-foreground leading-relaxed">
          {description}
        </span>
      </span>
      <span className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          onChange={(event) => onCheckedChange(event.target.checked)}
          disabled={disabled}
          data-testid={testId}
        />
        <span
          className={cn(
            'pointer-events-none absolute inset-0 rounded-full transition-colors',
            'bg-input peer-checked:bg-primary',
            'peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2',
          )}
        />
        <span
          className={cn(
            'pointer-events-none absolute top-0.5 start-0.5 size-4 rounded-full bg-background shadow-xs',
            'transition-[inset-inline-start] peer-checked:start-[1.125rem]',
          )}
        />
      </span>
    </label>
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
  const expertSelectId = useId();
  const queryClient = useQueryClient();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const expertsQuery = useExperts();
  const disconnect = useDisconnectConnection();
  const [confirmOpen, setConfirmOpen] = useState(false);
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
  const uiStatus = resolveWhatsAppUiStatus(connection);
  const connecting = isConnectingStatus(connection);
  const needsAttention =
    uiStatus.key === 'disconnected' ||
    uiStatus.key === 'failed' ||
    uiStatus.key === 'actionRequired';
  const statusHintKey: WhatsAppUiStatusKey | null =
    uiStatus.key === 'connected' ? null : uiStatus.key;

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

  const lastError =
    connection.last_error_code || connection.last_error_message
      ? friendlyDisplayError(t, {
          code: connection.last_error_code,
          message: connection.last_error_message,
        })
      : null;

  const showResume = connecting && Boolean(onResumeConnect);
  const savePrimary = dirty && !showResume;
  const reconnectPrimary = needsAttention && !dirty && !showResume;
  const phoneLabel = whatsappPhoneLabel(connection);

  return (
    <Card
      className="shadow-xs overflow-hidden"
      data-testid={`whatsapp-connection-card-${connection.id}`}
    >
      <CardHeader className="px-4 py-3.5 sm:px-5 min-h-0">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <AppIcon slug="whatsapp" name="WhatsApp" size="sm" className="size-9 w-9 h-9 p-1.5" />
          <CardHeading className="min-w-0 flex-1 space-y-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 space-y-1">
                <CardTitle className="text-sm">{titleFor(connection, t)}</CardTitle>
                {phoneLabel ? (
                  <CardDescription
                    className="text-xs tabular-nums tracking-tight"
                    dir="ltr"
                    data-testid="whatsapp-connection-phone"
                  >
                    {phoneLabel}
                  </CardDescription>
                ) : null}
              </div>
              <WhatsAppStatusBadge connection={connection} />
            </div>
          </CardHeading>
        </div>
      </CardHeader>

      <CardContent className="p-4 sm:p-5 space-y-5">
        {lastError ? (
          <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {lastError}
          </p>
        ) : statusHintKey ? (
          <p
            className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
            data-testid="whatsapp-status-hint"
          >
            {t(`apps.whatsapp.connection.statusHint.${statusHintKey}`)}
          </p>
        ) : null}

        <div className="space-y-2">
          <Label htmlFor={expertSelectId}>{t('apps.whatsapp.connection.expert')}</Label>
          <div className="relative">
            <select
              id={expertSelectId}
              className={cn(
                inputVariants({ variant: 'md' }),
                'appearance-none pe-9',
              )}
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
            <ChevronDown
              className="pointer-events-none absolute end-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {t('apps.whatsapp.connection.expertHint')}
          </p>
        </div>

        <div className="space-y-1">
          <p className="text-sm font-medium">{t('apps.whatsapp.connection.settings')}</p>
          <div className="divide-y divide-border rounded-lg border border-border px-4">
            <ChannelToggle
              checked={enabled}
              onCheckedChange={setEnabled}
              disabled={!canManage}
              label={t('apps.whatsapp.connection.enabled')}
              description={t('apps.whatsapp.connection.enabledHint')}
              testId="whatsapp-enabled"
            />
            <ChannelToggle
              checked={autoReplyEnabled}
              onCheckedChange={setAutoReplyEnabled}
              disabled={!canManage || !enabled}
              label={t('apps.whatsapp.connection.autoReply')}
              description={t('apps.whatsapp.connection.autoReplyHint')}
              testId="whatsapp-auto-reply"
            />
            <ChannelToggle
              checked={respondToGroups}
              onCheckedChange={setRespondToGroups}
              disabled={!canManage || !enabled}
              label={t('apps.whatsapp.connection.respondToGroups')}
              description={t('apps.whatsapp.connection.respondToGroupsHint')}
              testId="whatsapp-respond-to-groups"
            />
          </div>
        </div>

        {!canManage ? (
          <p className="text-sm text-muted-foreground" data-testid="whatsapp-member-readonly">
            {t('apps.whatsapp.connection.readOnly')}
          </p>
        ) : null}

        {actionError ? <p className="text-sm text-destructive">{t(actionError)}</p> : null}
      </CardContent>

      {canManage ? (
        <CardFooter className="px-4 py-3 sm:px-5 min-h-0 flex-wrap justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {showResume ? (
              <Button
                size="sm"
                onClick={() => onResumeConnect?.(connection)}
                data-testid="whatsapp-resume-connect"
              >
                {t('apps.whatsapp.connect.resume')}
              </Button>
            ) : null}
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex">
                  <Button
                    variant={savePrimary ? 'primary' : 'outline'}
                    size="sm"
                    onClick={() => updateMutation.mutate()}
                    disabled={!dirty || updateMutation.isPending}
                    data-testid="whatsapp-save-settings"
                  >
                    {t('common.save')}
                  </Button>
                </span>
              </TooltipTrigger>
              {!dirty ? (
                <TooltipContent>{t('apps.whatsapp.connection.saveDisabledHint')}</TooltipContent>
              ) : null}
            </Tooltip>
            {dirty ? (
              <span className="text-xs text-muted-foreground" data-testid="whatsapp-unsaved">
                {t('apps.whatsapp.connection.unsaved')}
              </span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {connecting ? null : (
              <Button
                variant={reconnectPrimary ? 'primary' : 'outline'}
                size="sm"
                onClick={() => reconnectMutation.mutate()}
                disabled={reconnectMutation.isPending}
                data-testid="whatsapp-reconnect"
              >
                {t('apps.connections.reconnect')}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/5"
              onClick={() => setConfirmOpen(true)}
              disabled={disconnect.isPending}
              data-testid="whatsapp-disconnect"
            >
              {t('apps.connections.disconnect')}
            </Button>
          </div>
        </CardFooter>
      ) : null}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apps.connections.disconnectTitle')}</DialogTitle>
            <DialogDescription>{t('apps.connections.disconnectHint')}</DialogDescription>
          </DialogHeader>
          {disconnect.isError ? (
            <p className="text-sm text-destructive">
              {t(
                errorMessageKey(
                  disconnect.error instanceof ApiError ? disconnect.error.code : 'unknown',
                ),
              )}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              disabled={disconnect.isPending}
              data-testid="whatsapp-disconnect-confirm"
              onClick={() =>
                disconnect.mutate(
                  {
                    slug: connection.app_slug,
                    connectionId: connection.id,
                  },
                  { onSuccess: () => setConfirmOpen(false) },
                )
              }
            >
              {t('apps.connections.disconnect')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
