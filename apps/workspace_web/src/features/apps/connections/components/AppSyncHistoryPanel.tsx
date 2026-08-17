import { useTranslation } from 'react-i18next';
import type { CatalogApp } from '@/services/api/apps';
import {
  useAppConnections,
  useConnectionSyncRuns,
} from '../hooks/useConnectionQueries';
import { SyncHistory } from './SyncHistory';

/**
 * Sync history for the first connection on a connector app (detail sheet tab).
 */
export function AppSyncHistoryPanel({ app }: { app: CatalogApp }) {
  const { t } = useTranslation();
  const connector = app.connector;
  const connectionsQuery = useAppConnections(app.slug, Boolean(connector));
  const firstConnection = connectionsQuery.data?.items[0];
  const syncQuery = useConnectionSyncRuns(
    app.slug,
    firstConnection?.id,
    Boolean(firstConnection),
  );

  if (!connector) return null;

  if (connectionsQuery.isLoading) {
    return <div className="h-16 rounded-xl bg-muted animate-pulse" />;
  }

  if (!firstConnection) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="sync-history-needs-connection"
      >
        {t('apps.connections.syncHistoryNeedsConnection')}
      </p>
    );
  }

  return (
    <div data-testid="app-sync-history-panel">
      <SyncHistory
        runs={syncQuery.data?.items ?? []}
        isLoading={syncQuery.isLoading}
      />
    </div>
  );
}
