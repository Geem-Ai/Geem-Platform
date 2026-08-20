import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import {
  planStatusBadge,
  platformRoleBadge,
  userStatusBadge,
  workspaceKindBadge,
  workspaceStatusBadge,
} from '@/lib/status';

type Props = {
  status: string;
  className?: string;
};

export function WorkspaceStatusBadge({ status, className }: Props) {
  const { t } = useTranslation();
  const spec = workspaceStatusBadge(status);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}

export function UserStatusBadge({ status, className }: Props) {
  const { t } = useTranslation();
  const spec = userStatusBadge(status);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}

export function PlatformRoleBadge({ role, className }: { role: string; className?: string }) {
  const { t } = useTranslation();
  const spec = platformRoleBadge(role);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}

export function WorkspaceKindBadge({ kind, className }: { kind: string; className?: string }) {
  const { t } = useTranslation();
  const spec = workspaceKindBadge(kind);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}

export function PlanStatusBadge({ status, className }: Props) {
  const { t } = useTranslation();
  const spec = planStatusBadge(status);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}
