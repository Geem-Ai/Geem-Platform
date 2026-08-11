import { useTranslation } from 'react-i18next';
import type { Expert } from '@/services/api/types';
import { ExpertCard } from './ExpertCard';

interface ExpertListSectionProps {
  titleKey: string;
  experts: Expert[];
  onAsk?: (expert: Expert) => void;
  emptyKey?: string;
}

export function ExpertListSection({
  titleKey,
  experts,
  onAsk,
  emptyKey,
}: ExpertListSectionProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-3">
      <h2 className="text-base font-semibold">{t(titleKey)}</h2>
      {experts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t(emptyKey ?? 'experts.noExperts')}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {experts.map((expert) => (
            <ExpertCard key={expert.id} expert={expert} onAsk={onAsk} />
          ))}
        </div>
      )}
    </div>
  );
}
