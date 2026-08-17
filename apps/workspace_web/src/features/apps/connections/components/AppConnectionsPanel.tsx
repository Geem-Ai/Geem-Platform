import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import type { CatalogApp } from '@/services/api/apps';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import {
  useAppConnections,
  useConnectionSyncRuns,
  useHealthCheckConnection,
  useRequestConnectionSync,
  useStartConnection,
} from '../hooks/useConnectionQueries';
import { ConnectionCard } from './ConnectionCard';
import { SyncHistory } from './SyncHistory';

export function AppConnectionsPanel({
  app,
  canManage,
}: {
  app: CatalogApp;
  canManage: boolean;
}) {
  const { t } = useTranslation();
  const connector = app.connector;
  const installed = app.installation_status === 'active';
  const connectionsQuery = useAppConnections(app.slug, Boolean(connector));
  const healthMut = useHealthCheckConnection();
  const syncMut = useRequestConnectionSync();
  const startMut = useStartConnection();

  const firstConnection = connectionsQuery.data?.items[0];
  const syncQuery = useConnectionSyncRuns(
    app.slug,
    firstConnection?.id,
    Boolean(firstConnection),
  );

  if (!connector) {
    return null;
  }

  const canStart =
    canManage &&
    installed &&
    connector.available &&
    connector.can_connect &&
    (connectionsQuery.data?.items.length ?? 0) === 0;

  return (
    <section className="space-y-3" data-testid="app-connections-panel">
      <h3 className="text-sm font-semibold">{t('apps.connections.title')}</h3>

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
              onClick={() => startMut.mutate({ slug: app.slug })}
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
        />
      ))}

      {firstConnection ? (
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
