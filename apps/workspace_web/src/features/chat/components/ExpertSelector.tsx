import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import type { Expert } from '@/services/api/types';
import { canAskExpert } from '@/features/experts/lib/capabilities';
import { ExpertStatusBadge } from '@/features/experts/components/ExpertStatusBadge';

interface ExpertSelectorProps {
  experts: Expert[];
  selectedId: string | null;
  onSelect: (expertId: string) => void;
  isLoading?: boolean;
}

export function ExpertSelector({
  experts,
  selectedId,
  onSelect,
  isLoading,
}: ExpertSelectorProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>;
  }

  const usable = experts.filter((e) => canAskExpert(e.status));

  if (usable.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm font-medium">{t('chat.noExperts')}</p>
        <p className="text-xs text-muted-foreground mt-1">{t('chat.noExpertsHint')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t('chat.selectExpertHint')}</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {usable.map((expert) => (
          <button
            key={expert.id}
            type="button"
            onClick={() => onSelect(expert.id)}
            className={`w-full text-start rounded-lg border p-3 transition-colors hover:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedId === expert.id ? 'border-ring bg-accent/30' : 'border-border'}`}
          >
            <div className="flex items-center gap-2">
              {expert.icon_url ? (
                <img
                  src={expert.icon_url}
                  alt={expert.name}
                  className="size-7 rounded-full shrink-0 object-cover"
                />
              ) : (
                <div className="size-7 rounded-full shrink-0 bg-muted flex items-center justify-center text-xs font-semibold text-muted-foreground">
                  {expert.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{expert.name}</p>
                {expert.description && (
                  <p className="text-xs text-muted-foreground line-clamp-1">
                    {expert.description}
                  </p>
                )}
              </div>
              <div className="ms-auto flex items-center gap-1 shrink-0">
                {expert.ownership === 'platform' && (
                  <Badge variant="secondary" appearance="light" size="sm">
                    {t('experts.type.platform')}
                  </Badge>
                )}
                <ExpertStatusBadge status={expert.status} />
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
