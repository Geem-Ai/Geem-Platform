import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import {
  expertStatusBadge,
  expertVisibilityBadge,
  planStatusBadge,
  platformRoleBadge,
  purchaseStatusBadge,
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

export function ExpertStatusBadge({ status, className }: Props) {
  const { t } = useTranslation();
  const spec = expertStatusBadge(status);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}

export function ExpertVisibilityBadge({
  visibility,
  className,
}: {
  visibility: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const spec = expertVisibilityBadge(visibility);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}

export function PurchaseStatusBadge({ status, className }: Props) {
  const { t } = useTranslation();
  const spec = purchaseStatusBadge(status);
  return (
    <Badge variant={spec.variant} appearance="light" size="sm" className={className}>
      {t(spec.labelKey)}
    </Badge>
  );
}
