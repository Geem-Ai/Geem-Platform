import { useTranslation } from 'react-i18next';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { expertStatusBadgeVariant, expertStatusLabelKey } from '../lib/status';

interface ExpertStatusBadgeProps {
  status: string;
  showDot?: boolean;
}

export function ExpertStatusBadge({ status, showDot = true }: ExpertStatusBadgeProps) {
  const { t } = useTranslation();
  return (
    <Badge variant={expertStatusBadgeVariant(status)} appearance="light" size="sm">
      {showDot ? (
        <BadgeDot
          className={status === 'processing' ? 'animate-pulse opacity-100' : undefined}
        />
      ) : null}
      {t(expertStatusLabelKey(status))}
    </Badge>
  );
}
