import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowUpRight, FileText, MessageSquare } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { Expert } from '@/services/api/types';
import { canAskExpert } from '../lib/capabilities';
import { ExpertAvatar } from './ExpertAvatar';
import { ExpertStatusBadge } from './ExpertStatusBadge';

interface ExpertCardProps {
  expert: Expert;
  onAsk?: (expert: Expert) => void;
  onOpen?: (expert: Expert) => void;
}

export function ExpertCard({ expert, onAsk, onOpen }: ExpertCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const canAsk = canAskExpert(expert.status);
  const isPlatform = expert.ownership === 'platform';

  function openExpert() {
    if (onOpen) {
      onOpen(expert);
      return;
    }
    void navigate(`/experts/${expert.id}`);
  }

  return (
    <Card
      className={cn(
        'group relative flex flex-col gap-0 overflow-hidden cursor-pointer',
        'transition-[background-color,box-shadow,border-color] duration-200',
        'hover:border-primary/25 hover:shadow-sm hover:bg-accent/20',
        'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/30',
      )}
      role="button"
      tabIndex={0}
      aria-label={expert.name}
      onClick={openExpert}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openExpert();
        }
      }}
    >
      <CardContent className="flex flex-col gap-4 p-4 sm:p-5 h-full">
        <div className="flex items-start gap-3">
          <ExpertAvatar
            name={expert.name}
            iconUrl={expert.icon_url}
            ownership={expert.ownership}
          />
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold tracking-tight truncate leading-5">
                {expert.name}
              </h3>
              <ExpertStatusBadge status={expert.status} />
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2 min-h-8 leading-relaxed">
              {expert.description?.trim() || t('experts.noDescription')}
            </p>
          </div>
        </div>

        <div className="mt-auto flex flex-wrap items-center gap-2">
          <Badge variant="secondary" appearance="light" size="sm">
            {isPlatform ? t('experts.platformBadge') : t('experts.type.workspace')}
          </Badge>
          {!isPlatform && (
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <FileText className="size-3.5 opacity-70" aria-hidden />
              {t('experts.knowledgeCount', {
                count: expert.knowledge_document_count ?? 0,
              })}
            </span>
          )}
        </div>

        <div
          className="flex items-center gap-2 pt-1 border-t border-border/70"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <Button variant="outline" size="sm" className="flex-1" onClick={openExpert}>
            {t('experts.open')}
            <ArrowUpRight className="size-3.5 opacity-70" />
          </Button>
          {canAsk && (
            <Button
              size="sm"
              className="flex-1"
              onClick={() => onAsk?.(expert)}
              asChild={!onAsk}
            >
              {onAsk ? (
                <>
                  <MessageSquare className="size-3.5" />
                  {t('experts.ask')}
                </>
              ) : (
                <Link to={`/chat?expert=${expert.id}`}>
                  <MessageSquare className="size-3.5" />
                  {t('experts.ask')}
                </Link>
              )}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
