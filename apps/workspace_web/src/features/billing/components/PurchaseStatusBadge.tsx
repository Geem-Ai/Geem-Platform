import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import type { PurchaseStatus } from '@/services/api/billing';
import {
  purchaseStatusBadgeVariant,
  purchaseStatusLabelKey,
} from '../lib/status';

export function PurchaseStatusBadge({
  status,
  testId,
}: {
  status: PurchaseStatus;
  testId?: string;
}) {
  const { t } = useTranslation();
  return (
    <Badge
      variant={purchaseStatusBadgeVariant(status)}
      appearance="light"
      size="sm"
      data-testid={testId}
      data-status={status}
    >
      {t(purchaseStatusLabelKey(status))}
    </Badge>
  );
}
