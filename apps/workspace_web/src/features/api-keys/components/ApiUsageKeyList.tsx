import { Link } from 'react-router-dom';
import { KeyRound, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { ApiUsageKeyRow, ApiUsagePeriodKey } from '@/services/api/api-keys';
import { formatCount, formatRelativeTime } from '@/features/usage/lib/quota';
import { ApiKeyStatusBadge } from './ApiKeyStatusBadge';
import { apiUsageHref } from '../lib/period';
import { tokenSharePercent } from '../lib/share';
import { apiKeyStatus, maskedApiKey } from '../lib/status';

type ApiUsageKeyListProps = {
  keys: ApiUsageKeyRow[];
  period: ApiUsagePeriodKey;
  keyFilter: string | null;
  billedTotal: number;
};

export function ApiUsageKeyList({
  keys,
  period,
  keyFilter,
  billedTotal,
}: ApiUsageKeyListProps) {
  const { t, i18n } = useTranslation();

  if (keys.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center py-12 px-4 text-center"
        data-testid="api-usage-no-keys"
      >
        <div className="size-11 rounded-xl bg-muted text-muted-foreground flex items-center justify-center mb-3">
          <KeyRound className="size-4" aria-hidden />
        </div>
        <p className="text-sm font-medium">{t('apiUsage.noKeysTitle')}</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-sm leading-relaxed">
          {t('apiUsage.noKeys')}
        </p>
        <Button size="sm" asChild className="mt-4">
          <Link to="/api/keys">
            <Plus className="size-3.5" />
            {t('apiUsage.createKey')}
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {keys.length > 1 ? (
        <div className="flex flex-wrap gap-1.5" data-testid="api-usage-key-filters">
          <Button variant={!keyFilter ? 'primary' : 'outline'} size="sm" asChild>
            <Link to={apiUsageHref(period, null, 1)}>{t('apiUsage.allKeys')}</Link>
          </Button>
          {keys.map((key) => (
            <Button
              key={key.api_key_id}
              variant={keyFilter === key.api_key_id ? 'primary' : 'outline'}
              size="sm"
              asChild
            >
              <Link to={apiUsageHref(period, key.api_key_id, 1)}>
                {key.name || key.prefix}
              </Link>
            </Button>
          ))}
        </div>
      ) : null}

      <ul className="divide-y divide-border rounded-lg border border-border overflow-hidden">
        {keys.map((key) => {
          const selected = keyFilter === key.api_key_id;
          const status = apiKeyStatus(key);
          const share = tokenSharePercent(key.billed_tokens, billedTotal);
          return (
            <li key={key.api_key_id} data-testid={`api-usage-key-${key.api_key_id}`}>
              <Link
                to={apiUsageHref(period, selected ? null : key.api_key_id, 1)}
                className={cn(
                  'block p-4 transition-colors hover:bg-muted/40 focus-visible:outline-hidden focus-visible:bg-muted/40',
                  selected && 'bg-primary/5',
                )}
                aria-current={selected ? 'true' : undefined}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium truncate">
                        {key.name || t('apiUsage.unknownKey')}
                      </p>
                      <ApiKeyStatusBadge status={status} />
                    </div>
                    <p className="font-mono text-xs text-muted-foreground" dir="ltr">
                      {maskedApiKey(key)}
                    </p>
                  </div>
                  <div className="sm:text-end shrink-0">
                    <p className="text-sm font-medium tabular-nums">
                      {t('apiUsage.keyBilled', {
                        value: formatCount(key.billed_tokens, i18n.language),
                      })}
                    </p>
                    <p className="text-[11px] text-muted-foreground tabular-nums mt-0.5">
                      {t('apiUsage.shareOfPeriod', {
                        value: Math.round(share),
                      })}
                    </p>
                  </div>
                </div>
                <Progress
                  value={share}
                  label={key.name || key.prefix}
                  className="h-1.5 mt-3"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  {key.last_used_at
                    ? t('apiUsage.lastUsed', {
                        time: formatRelativeTime(key.last_used_at, i18n.language),
                      })
                    : t('apiKeys.neverUsed')}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
