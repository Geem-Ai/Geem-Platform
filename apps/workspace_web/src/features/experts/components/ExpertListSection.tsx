import { Plus, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import type { Expert } from '@/services/api/types';
import { ExpertCard } from './ExpertCard';

interface ExpertListSectionProps {
  titleKey: string;
  descriptionKey?: string;
  experts: Expert[];
  onAsk?: (expert: Expert) => void;
  onOpen?: (expert: Expert) => void;
  emptyTitleKey?: string;
  emptyKey?: string;
  onCreate?: () => void;
  createLabelKey?: string;
  showCreateInEmpty?: boolean;
}

export function ExpertListSection({
  titleKey,
  descriptionKey,
  experts,
  onAsk,
  onOpen,
  emptyTitleKey,
  emptyKey,
  onCreate,
  createLabelKey = 'experts.create',
  showCreateInEmpty = false,
}: ExpertListSectionProps) {
  const { t } = useTranslation();

  return (
    <section className="space-y-4" aria-labelledby={`${titleKey}-heading`}>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2
              id={`${titleKey}-heading`}
              className="text-base font-semibold tracking-tight"
            >
              {t(titleKey)}
            </h2>
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-muted px-1.5 text-[11px] font-medium text-muted-foreground tabular-nums">
              {experts.length}
            </span>
          </div>
          {descriptionKey && (
            <p className="text-xs text-muted-foreground mt-1">{t(descriptionKey)}</p>
          )}
        </div>
      </div>

      {experts.length === 0 ? (
        <Card className="border-dashed shadow-none">
          <CardContent className="flex flex-col items-center text-center gap-3 py-10 px-6">
            <div className="size-11 rounded-xl bg-muted flex items-center justify-center text-muted-foreground">
              <Sparkles className="size-5" aria-hidden />
            </div>
            <div className="space-y-1 max-w-sm">
              <p className="text-sm font-medium">
                {t(emptyTitleKey ?? 'experts.noExperts')}
              </p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {t(emptyKey ?? 'experts.noExpertsHint')}
              </p>
            </div>
            {showCreateInEmpty && onCreate && (
              <Button size="sm" onClick={onCreate} className="mt-1">
                <Plus className="size-3.5" />
                {t(createLabelKey)}
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {experts.map((expert) => (
            <ExpertCard
              key={expert.id}
              expert={expert}
              onAsk={onAsk}
              onOpen={onOpen}
            />
          ))}
        </div>
      )}
    </section>
  );
}
