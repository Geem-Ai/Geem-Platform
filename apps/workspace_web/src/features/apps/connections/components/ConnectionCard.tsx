import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { AppConnection } from '@/services/api/apps';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { useDisconnectConnection } from '../hooks/useConnectionQueries';
import { ConnectionHealthBadge } from './ConnectionHealthBadge';
import { ConnectionStatusBadge } from './ConnectionStatusBadge';

function formatWhen(value: string | null, locale: string): string {
  if (!value) return '';
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function ConnectionCard({
  connection,
  canManage,
  onHealthCheck,
  onSync,
  healthPending,
  syncPending,
}: {
  connection: AppConnection;
  canManage: boolean;
  onHealthCheck?: () => void;
  onSync?: () => void;
  healthPending?: boolean;
  syncPending?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const disconnect = useDisconnectConnection();
  const title =
    connection.display_name ||
    connection.external_account_name ||
    t('apps.connections.untitled');

  return (
    <div
      className="rounded-xl border border-border px-4 py-3 space-y-3"
      data-testid={`connection-card-${connection.id}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium">{title}</p>
        <ConnectionStatusBadge status={connection.status} />
        <ConnectionHealthBadge health={connection.health} />
      </div>
      {connection.last_success_at ? (
        <p className="text-xs text-muted-foreground">
          {t('apps.connections.lastSynced', {
            date: formatWhen(connection.last_success_at, i18n.language),
          })}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          {t('apps.connections.neverSynced')}
        </p>
      )}
      {connection.last_error_message ? (
        <p className="text-xs text-destructive">{connection.last_error_message}</p>
      ) : null}
      {canManage ? (
        <div className="flex flex-wrap gap-2">
          {connection.capabilities.can_health_check ? (
            <Button
              size="sm"
              variant="outline"
              disabled={healthPending}
              onClick={onHealthCheck}
              data-testid="connection-health-check"
            >
              {t('apps.connections.checkConnection')}
            </Button>
          ) : null}
          {connection.capabilities.can_sync ? (
            <Button
              size="sm"
              variant="outline"
              disabled={syncPending}
              onClick={onSync}
              data-testid="connection-sync"
            >
              {t('apps.connections.syncNow')}
            </Button>
          ) : null}
          {connection.capabilities.can_disconnect ? (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setConfirmOpen(true)}
              data-testid="connection-disconnect"
            >
              {t('apps.connections.disconnect')}
            </Button>
          ) : null}
        </div>
      ) : null}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apps.connections.disconnectTitle')}</DialogTitle>
            <DialogDescription>
              {t('apps.connections.disconnectHint')}
            </DialogDescription>
          </DialogHeader>
          {disconnect.isError ? (
            <p className="text-sm text-destructive">
              {t(
                errorMessageKey(
                  disconnect.error instanceof ApiError
                    ? disconnect.error.code
                    : 'unknown',
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
              data-testid="connection-disconnect-confirm"
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
    </div>
  );
}
