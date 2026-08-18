import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';

const VARIANT: Record<string, 'primary' | 'info' | 'secondary'> = {
  owner: 'primary',
  admin: 'info',
  member: 'secondary',
};

export function RoleBadge({ role }: { role: string }) {
  const { t } = useTranslation();
  const key = `roles.${role}`;
  const label = t(key, { defaultValue: role });
  return (
    <Badge
      variant={VARIANT[role] ?? 'outline'}
      appearance="light"
      size="sm"
      data-testid={`role-badge-${role}`}
    >
      {label}
    </Badge>
  );
}
