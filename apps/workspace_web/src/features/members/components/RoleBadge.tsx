import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { asRoleSummary, roleLabel } from '@/features/authz/role-summary';
import type { RoleSummary } from '@/services/api/types';

type RoleBadgeProps = {
  role: RoleSummary | string;
};

export function RoleBadge({ role }: RoleBadgeProps) {
  const { t } = useTranslation();
  const summary = asRoleSummary(role);
  if (!summary) return null;
  const systemKey = summary.system_key;
  const variant = summary.is_owner_role
    ? 'primary'
    : summary.is_system
      ? 'info'
      : 'secondary';
  return (
    <Badge
      variant={variant}
      appearance="light"
      size="sm"
      data-testid={`role-badge-${systemKey ?? summary.id}`}
    >
      {roleLabel(summary, t)}
    </Badge>
  );
}
