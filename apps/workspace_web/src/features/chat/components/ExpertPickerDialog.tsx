import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Search, Sparkles } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { Expert } from '@/services/api/types';
import { canAskExpert } from '@/features/experts/lib/capabilities';
import { localizeExpertDisplay } from '@/features/experts/lib/localize';
import { ExpertStatusBadge } from '@/features/experts/components/ExpertStatusBadge';

interface ExpertPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  experts: Expert[];
  selectedId: string | null;
  onSelect: (expertId: string) => void;
  isLoading?: boolean;
}

function matchesQuery(
  expert: Expert,
  query: string,
  display: { name: string; description: string | null },
): boolean {
  if (!query) return true;
  const q = query.trim().toLowerCase();
  return (
    display.name.toLowerCase().includes(q) ||
    (display.description ?? '').toLowerCase().includes(q) ||
    expert.name.toLowerCase().includes(q) ||
    (expert.description ?? '').toLowerCase().includes(q)
  );
}

function ExpertRow({
  expert,
  selected,
  onSelect,
}: {
  expert: Expert;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const usable = canAskExpert(expert.status);
  const isPlatform = expert.ownership === 'platform';
  const isGeneral = expert.knowledge_mode === 'general';
  const display = localizeExpertDisplay(expert, t);

  return (
    <button
      type="button"
      disabled={!usable}
      onClick={onSelect}
      data-testid={`expert-option-${expert.id}`}
      data-knowledge-mode={expert.knowledge_mode ?? 'rag'}
      aria-pressed={selected}
      className={cn(
        'w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-start transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        usable
          ? selected
            ? 'border-ring bg-accent/40'
            : 'border-border hover:bg-muted/60'
          : 'border-border opacity-50 cursor-not-allowed',
      )}
    >
      {expert.icon_url ? (
        <img
          src={expert.icon_url}
          alt=""
          className="size-9 rounded-lg shrink-0 object-cover bg-muted"
        />
      ) : (
        <div className="size-9 rounded-lg shrink-0 bg-muted flex items-center justify-center">
          <Sparkles className="size-4 text-muted-foreground" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium truncate">{display.name}</p>
          {isGeneral && (
            <Badge variant="primary" appearance="light" size="sm">
              {t('chat.geemGeneralBadge')}
            </Badge>
          )}
          {isPlatform && !isGeneral && (
            <Badge variant="secondary" appearance="light" size="sm">
              {t('experts.platformBadge')}
            </Badge>
          )}
        </div>
        {display.description && (
          <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
            {display.description}
          </p>
        )}
        {!isPlatform && (
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {t('experts.knowledgeCount', {
              count: expert.knowledge_document_count ?? 0,
            })}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <ExpertStatusBadge status={expert.status} />
        {selected && <Check className="size-4 text-primary" />}
      </div>
    </button>
  );
}

function ExpertSection({
  title,
  hint,
  experts,
  selectedId,
  onSelect,
  emptyLabel,
}: {
  title: string;
  hint?: string;
  experts: Expert[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  emptyLabel: string;
}) {
  return (
    <section className="space-y-2">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {title}
        </h3>
        {hint && <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p>}
      </div>
      {experts.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">{emptyLabel}</p>
      ) : (
        <div className="space-y-1.5">
          {experts.map((expert) => (
            <ExpertRow
              key={expert.id}
              expert={expert}
              selected={selectedId === expert.id}
              onSelect={() => onSelect(expert.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function ExpertPickerDialog({
  open,
  onOpenChange,
  experts,
  selectedId,
  onSelect,
  isLoading,
}: ExpertPickerDialogProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (open) setQuery('');
  }, [open]);

  const filtered = useMemo(
    () =>
      experts.filter((e) => matchesQuery(e, query, localizeExpertDisplay(e, t))),
    [experts, query, t],
  );

  const workspaceExperts = useMemo(
    () => filtered.filter((e) => e.ownership === 'workspace'),
    [filtered],
  );
  const geemExperts = useMemo(() => {
    const platform = filtered.filter((e) => e.ownership === 'platform');
    return [...platform].sort((a, b) => {
      const ag = a.knowledge_mode === 'general' ? 0 : 1;
      const bg = b.knowledge_mode === 'general' ? 0 : 1;
      if (ag !== bg) return ag - bg;
      return a.name.localeCompare(b.name);
    });
  }, [filtered]);

  function handleSelect(id: string) {
    onSelect(id);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-lg max-h-[min(85vh,640px)] flex flex-col gap-4"
        data-testid="expert-picker-dialog"
      >
        <DialogHeader>
          <DialogTitle>{t('chat.selectExpert')}</DialogTitle>
          <DialogDescription>{t('chat.selectExpertHint')}</DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('chat.expertSearchPlaceholder')}
            className="ps-9"
            autoFocus
            data-testid="expert-picker-search"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto space-y-5 pe-1">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">{t('chat.loadingExperts')}</p>
          ) : experts.length === 0 ? (
            <div className="text-center py-8 space-y-1">
              <p className="text-sm font-medium">{t('chat.noExperts')}</p>
              <p className="text-xs text-muted-foreground">{t('chat.noExpertsHint')}</p>
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {t('chat.expertSearchEmpty', { query })}
            </p>
          ) : (
            <>
              <ExpertSection
                title={t('experts.myExperts')}
                hint={t('experts.myExpertsHint')}
                experts={workspaceExperts}
                selectedId={selectedId}
                onSelect={handleSelect}
                emptyLabel={
                  query
                    ? t('chat.expertSearchEmptySection')
                    : t('experts.noExpertsHint')
                }
              />
              <ExpertSection
                title={t('chat.geemExperts')}
                hint={t('experts.platformExpertsHint')}
                experts={geemExperts}
                selectedId={selectedId}
                onSelect={handleSelect}
                emptyLabel={
                  query
                    ? t('chat.expertSearchEmptySection')
                    : t('experts.noPlatformExpertsHint')
                }
              />
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
