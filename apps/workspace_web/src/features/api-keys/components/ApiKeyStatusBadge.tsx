import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import type { ApiKeyStatus } from '@/services/api/api-keys';
import { statusBadgeVariant } from '../lib/status';

export function ApiKeyStatusBadge({ status }: { status: ApiKeyStatus }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant={statusBadgeVariant(status)}
      appearance="light"
      size="sm"
      data-testid={`api-key-status-${status}`}
    >
      {t(`apiKeys.status.${status}`)}
    </Badge>
  );
}
