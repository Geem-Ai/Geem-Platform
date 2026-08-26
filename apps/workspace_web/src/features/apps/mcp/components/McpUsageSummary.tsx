import { useTranslation } from 'react-i18next';
import { Progress } from '@/components/ui/progress';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { useMcpUsage } from '../hooks/useMcpQueries';

function formatDate(value: string | null | undefined, locale: string): string {
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

export function McpUsageSummary({ enabled = true }: { enabled?: boolean }) {
  const { t, i18n } = useTranslation();
  const query = useMcpUsage(enabled);

  if (!enabled) return null;
  if (query.isLoading) {
    return <div className="h-28 animate-pulse rounded-xl bg-muted" data-testid="mcp-usage-loading" />;
  }
  if (query.isError || !query.data) {
    const message =
      query.error instanceof ApiError
        ? t(errorMessageKey(query.error.code))
        : t('apps.mcp.usageLoadError');
    return (
      <div
        className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        data-testid="mcp-usage-error"
      >
        {message}
      </div>
    );
  }

  const { connections, tool_calls_daily: calls } = query.data;
  const percent = calls.limit > 0 ? (calls.used / calls.limit) * 100 : 0;
  const number = new Intl.NumberFormat(i18n.language);

  return (
    <section
      className="rounded-xl border border-border p-4 space-y-4"
      data-testid="mcp-usage-summary"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs text-muted-foreground">{t('apps.mcp.connectionsUsage')}</p>
          <p className="text-sm font-semibold tabular-nums">
            {t('apps.mcp.usageValue', {
              used: number.format(connections.used),
              limit: number.format(connections.limit),
            })}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{t('apps.mcp.toolCallsUsage')}</p>
          <p className="text-sm font-semibold tabular-nums" data-testid="mcp-tool-call-usage">
            {t('apps.mcp.usageValue', {
              used: number.format(calls.used),
              limit: number.format(calls.limit),
            })}
          </p>
        </div>
      </div>
      <Progress
        value={percent}
        label={t('apps.mcp.toolCallsProgress')}
        indicatorClassName={calls.used >= calls.limit ? 'bg-destructive' : undefined}
      />
      <p className="text-xs text-muted-foreground">
        {t('apps.mcp.resetsAt', {
          date: formatDate(calls.reset_at, i18n.language),
        })}
      </p>
    </section>
  );
}
