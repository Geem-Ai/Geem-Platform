import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';

const STATUS_VARIANT: Record<
  string,
  'primary' | 'success' | 'warning' | 'destructive' | 'secondary' | 'info'
> = {
  pending: 'secondary',
  connecting: 'info',
  active: 'success',
  degraded: 'warning',
  error: 'destructive',
  disconnected: 'secondary',
  revoked: 'destructive',
};

export function ConnectionStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  const key = `apps.connections.status.${status}`;
  const label = t(key, { defaultValue: status });
  return (
    <Badge
      variant={STATUS_VARIANT[status] ?? 'secondary'}
      appearance="light"
      size="sm"
      data-testid={`connection-status-${status}`}
    >
      {label}
    </Badge>
  );
}
