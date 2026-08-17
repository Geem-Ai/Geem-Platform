import { useTranslation } from 'react-i18next';
import type { ConnectorSyncRun } from '@/services/api/apps';
import { Badge } from '@/components/ui/badge';

function formatWhen(value: string | null, locale: string): string {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function SyncHistory({
  runs,
  isLoading,
}: {
  runs: ConnectorSyncRun[];
  isLoading?: boolean;
}) {
  const { t, i18n } = useTranslation();

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="sync-history-loading">
        <div className="h-10 rounded-lg bg-muted animate-pulse" />
        <div className="h-10 rounded-lg bg-muted animate-pulse" />
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="sync-history-empty"
      >
        {t('apps.connections.syncHistoryEmpty')}
      </p>
    );
  }

  return (
    <ul className="space-y-2" data-testid="sync-history-list">
      {runs.map((run) => (
        <li
          key={run.id}
          className="rounded-lg border border-border px-3 py-2 text-sm space-y-1"
          data-testid={`sync-run-${run.id}`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">
              {t(`apps.connections.syncTrigger.${run.trigger}`, {
                defaultValue: run.trigger,
              })}
            </span>
            <Badge variant="secondary" appearance="light" size="sm">
              {t(`apps.connections.syncStatus.${run.status}`, {
                defaultValue: run.status,
              })}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {formatWhen(run.started_at ?? run.created_at, i18n.language)}
            {run.completed_at
              ? ` → ${formatWhen(run.completed_at, i18n.language)}`
              : ''}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('apps.connections.syncCounters', {
              seen: run.items_seen,
              created: run.items_created,
              updated: run.items_updated,
              deleted: run.items_deleted,
              failed: run.items_failed,
            })}
          </p>
          {run.error_message ? (
            <p className="text-xs text-destructive">{run.error_message}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
