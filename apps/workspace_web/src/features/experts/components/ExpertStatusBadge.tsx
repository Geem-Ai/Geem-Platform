import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { expertStatusBadgeVariant, expertStatusLabelKey } from '../lib/status';

interface ExpertStatusBadgeProps {
  status: string;
}

export function ExpertStatusBadge({ status }: ExpertStatusBadgeProps) {
  const { t } = useTranslation();
  return (
    <Badge variant={expertStatusBadgeVariant(status)} appearance="light" size="sm">
      {t(expertStatusLabelKey(status))}
    </Badge>
  );
}
