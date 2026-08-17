import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';

const HEALTH_VARIANT: Record<
  string,
  'primary' | 'success' | 'warning' | 'destructive' | 'secondary'
> = {
  unknown: 'secondary',
  healthy: 'success',
  degraded: 'warning',
  failed: 'destructive',
};

export function ConnectionHealthBadge({ health }: { health: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant={HEALTH_VARIANT[health] ?? 'secondary'}
      appearance="light"
      size="sm"
      data-testid={`connection-health-${health}`}
    >
      {t(`apps.connections.health.${health}`, { defaultValue: health })}
    </Badge>
  );
}
