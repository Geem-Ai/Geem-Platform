import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import type { CatalogApp } from '@/services/api/apps';
import { ApiError, errorMessageKey, isKnownApiErrorCode } from '@/services/api/errors';
import {
  useAppConnections,
  useConnectionSyncRuns,
  useHealthCheckConnection,
  useRequestConnectionSync,
  useStartConnection,
} from '../hooks/useConnectionQueries';
import { ConnectionCard } from './ConnectionCard';
import { SyncHistory } from './SyncHistory';

function oauthReturnPath(slug: string): string {
  return `/apps/${slug}`;
}

export function AppConnectionsPanel({
  app,
  canManage,
  showSyncHistory = true,
  showTitle = true,
}: {
  app: CatalogApp;
  canManage: boolean;
  /** When false, parent renders Sync history in a separate tab. */
  showSyncHistory?: boolean;
  showTitle?: boolean;
}) {
  const { t } = useTranslation();
  const connector = app.connector;
  const installed = app.installation_status === 'active';
  const connectionsQuery = useAppConnections(app.slug, Boolean(connector));
  const healthMut = useHealthCheckConnection();
  const syncMut = useRequestConnectionSync();
  const startMut = useStartConnection();
  const [oauthNotice, setOauthNotice] = useState<'success' | 'error' | null>(
    null,
  );

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('connector') !== (connector?.key ?? '')) return;
    const oauth = params.get('oauth');
    if (oauth === 'success') {
      setOauthNotice('success');
      toast.success(t('apps.connections.oauthSuccess'));
      void connectionsQuery.refetch();
    } else if (oauth === 'error') {
      setOauthNotice('error');
      const raw = params.get('error') || 'unknown';
      const code = isKnownApiErrorCode(raw) ? raw : 'unknown';
      toast.error(t(errorMessageKey(code)));
    }
    if (oauth) {
      params.delete('oauth');
      params.delete('error');
      params.delete('connector');
      params.delete('connection_id');
      const next = `${window.location.pathname}${params.toString() ? `?${params}` : ''}`;
      window.history.replaceState({}, '', next);
    }
    // Only on mount / connector key change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connector?.key]);

  const firstConnection = connectionsQuery.data?.items[0];
  const syncQuery = useConnectionSyncRuns(
    app.slug,
    firstConnection?.id,
    Boolean(firstConnection) && showSyncHistory,
  );

  if (!connector) {
    return null;
  }

  const canStart =
    canManage && installed && connector.available && connector.can_connect;

  function startOAuth(connectionId?: string) {
    startMut.mutate(
      {
        slug: app.slug,
        connectionId,
        returnPath: oauthReturnPath(app.slug),
      },
      {
        onSuccess: (data) => {
          if (data.authorization_url) {
            window.location.assign(data.authorization_url);
            return;
          }
          toast.success(t('apps.connections.connected'));
        },
      },
    );
  }

  return (
    <section className="space-y-3" data-testid="app-connections-panel">
      {showTitle ? (
        <h3 className="text-sm font-semibold">{t('apps.connections.title')}</h3>
      ) : null}

      {!installed ? (
        <p className="text-sm text-muted-foreground">
          {t('apps.connections.installFirst')}
        </p>
      ) : null}

      {installed && !connector.available ? (
        <div
          role="note"
          className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
          data-testid="connector-unavailable"
        >
          <p>{t('apps.connections.setupComingSoon')}</p>
          <p className="mt-1">{t('apps.connections.notConnected')}</p>
        </div>
      ) : null}

      {oauthNotice === 'success' ? (
        <p className="text-sm text-foreground" data-testid="oauth-success">
          {t('apps.connections.oauthSuccess')}
        </p>
      ) : null}

      {oauthNotice === 'error' ? (
        <p className="text-sm text-destructive" data-testid="oauth-error">
          {t('apps.connections.connectionError')}
        </p>
      ) : null}

      {installed && connector.available && connectionsQuery.isLoading ? (
        <div className="h-16 rounded-xl bg-muted animate-pulse" />
      ) : null}

      {connectionsQuery.isError ? (
        <p className="text-sm text-destructive">
          {t(
            errorMessageKey(
              connectionsQuery.error instanceof ApiError
                ? connectionsQuery.error.code
                : 'unknown',
            ),
          )}
        </p>
      ) : null}

      {startMut.isError ? (
        <p className="text-sm text-destructive" data-testid="connection-start-error">
          {t(
            errorMessageKey(
              startMut.error instanceof ApiError ? startMut.error.code : 'unknown',
            ),
          )}
        </p>
      ) : null}

      {installed &&
      connector.available &&
      connectionsQuery.data &&
      connectionsQuery.data.items.length === 0 ? (
        <div className="space-y-2" data-testid="connections-empty">
          <p className="text-sm text-muted-foreground">
            {t('apps.connections.empty')}
          </p>
          {canStart ? (
            <Button
              size="sm"
              disabled={startMut.isPending}
              data-testid="connection-connect"
              onClick={() => startOAuth()}
            >
              {t('apps.connections.connect')}
            </Button>
          ) : null}
        </div>
      ) : null}

      {connectionsQuery.data?.items.map((connection) => (
        <ConnectionCard
          key={connection.id}
          connection={connection}
          canManage={canManage}
          healthPending={healthMut.isPending}
          syncPending={syncMut.isPending}
          reconnectPending={startMut.isPending}
          onHealthCheck={() =>
            healthMut.mutate({
              slug: app.slug,
              connectionId: connection.id,
            })
          }
          onSync={() =>
            syncMut.mutate({
              slug: app.slug,
              connectionId: connection.id,
            })
          }
          onReconnect={() => startOAuth(connection.id)}
        />
      ))}

      {showSyncHistory && firstConnection ? (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">
            {t('apps.connections.syncHistory')}
          </h4>
          <SyncHistory
            runs={syncQuery.data?.items ?? []}
            isLoading={syncQuery.isLoading}
          />
        </div>
      ) : null}
    </section>
  );
}
