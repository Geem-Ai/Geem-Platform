import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import type { Expert } from '@/services/api/types';
import { canAskExpert } from '../lib/capabilities';
import { ExpertStatusBadge } from './ExpertStatusBadge';

interface ExpertCardProps {
  expert: Expert;
  onAsk?: (expert: Expert) => void;
}

export function ExpertCard({ expert, onAsk }: ExpertCardProps) {
  const { t } = useTranslation();
  const canAsk = canAskExpert(expert.status);

  return (
    <Card className="flex flex-col gap-0">
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            {expert.icon_url ? (
              <img
                src={expert.icon_url}
                alt={expert.name}
                className="size-8 rounded-full shrink-0 object-cover"
              />
            ) : (
              <div className="size-8 rounded-full shrink-0 bg-muted flex items-center justify-center text-sm font-semibold text-muted-foreground">
                {expert.name.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{expert.name}</p>
              {expert.description && (
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {expert.description}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Badge variant="secondary" appearance="light" size="sm">
              {t(`experts.type.${expert.ownership}`)}
            </Badge>
            <ExpertStatusBadge status={expert.status} />
          </div>
        </div>

        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {expert.ownership === 'workspace' && expert.knowledge_document_count > 0
              ? t('experts.knowledgeCount', { count: expert.knowledge_document_count })
              : expert.ownership === 'platform'
                ? t('experts.platformBadge')
                : null}
          </span>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`/experts/${expert.id}`}>{t('experts.open')}</Link>
            </Button>
            {canAsk && (
              <Button
                size="sm"
                onClick={() => onAsk?.(expert)}
                asChild={!onAsk}
              >
                {onAsk ? (
                  t('experts.ask')
                ) : (
                  <Link to={`/chat?expert=${expert.id}`}>{t('experts.ask')}</Link>
                )}
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
