import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { ApiKey } from '@/services/api/api-keys';
import { formatPeriodDateTime, formatRelativeTime } from '@/features/usage/lib/quota';
import { apiKeyStatus, maskedApiKey } from '../lib/status';
import { ApiKeyStatusBadge } from './ApiKeyStatusBadge';

type ApiKeysListProps = {
  keys: ApiKey[];
  canManage: boolean;
  onRevoke: (key: ApiKey) => void;
};

export function ApiKeysList({ keys, canManage, onRevoke }: ApiKeysListProps) {
  const { t, i18n } = useTranslation();

  return (
    <div className="overflow-x-auto" data-testid="api-keys-list">
      <table className="w-full min-w-[44rem] text-sm">
        <thead>
          <tr className="border-b border-border text-start text-xs text-muted-foreground">
            <th className="py-2 pe-3 font-medium">{t('apiKeys.name')}</th>
            <th className="py-2 pe-3 font-medium">{t('apiKeys.key')}</th>
            <th className="py-2 pe-3 font-medium">{t('apiKeys.scope')}</th>
            <th className="py-2 pe-3 font-medium">{t('apiKeys.created')}</th>
            <th className="py-2 pe-3 font-medium">{t('apiKeys.lastUsed')}</th>
            <th className="py-2 pe-3 font-medium">{t('apiKeys.expiration')}</th>
            <th className="py-2 pe-3 font-medium">{t('apiKeys.statusLabel')}</th>
            {canManage ? (
              <th className="py-2 font-medium text-end">{t('apiKeys.actions')}</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const status = apiKeyStatus(key);
            return (
              <tr key={key.id} className="border-b border-border last:border-0" data-testid={`api-key-row-${key.id}`}>
                <td className="py-3 pe-3 font-medium">{key.name}</td>
                <td className="py-3 pe-3">
                  <code dir="ltr" className="text-xs font-mono whitespace-nowrap">
                    {maskedApiKey(key)}
                  </code>
                </td>
                <td className="py-3 pe-3">
                  <div className="flex flex-wrap gap-1">
                    {key.scopes.map((scope) => (
                      <Badge key={scope} variant="secondary" appearance="light" size="sm">
                        {scope === 'chat:write' ? t('apiKeys.scopeChatShort') : scope}
                      </Badge>
                    ))}
                  </div>
                </td>
                <td className="py-3 pe-3 text-muted-foreground whitespace-nowrap">
                  {formatPeriodDateTime(key.created_at, i18n.language) ?? '—'}
                </td>
                <td className="py-3 pe-3 text-muted-foreground whitespace-nowrap">
                  {key.last_used_at
                    ? formatRelativeTime(key.last_used_at, i18n.language)
                    : t('apiKeys.neverUsed')}
                </td>
                <td className="py-3 pe-3 text-muted-foreground whitespace-nowrap">
                  {key.expires_at
                    ? formatPeriodDateTime(key.expires_at, i18n.language)
                    : t('apiKeys.neverExpires')}
                </td>
                <td className="py-3 pe-3">
                  <ApiKeyStatusBadge status={status} />
                </td>
                {canManage ? (
                  <td className="py-3 text-end">
                    {status === 'active' ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => onRevoke(key)}
                        data-testid={`revoke-api-key-${key.id}`}
                      >
                        {t('apiKeys.revoke')}
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
