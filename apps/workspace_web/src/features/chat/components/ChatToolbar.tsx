import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { ConversationExpertSummary } from '@/services/api/types';
import { localizeExpertDisplay } from '@/features/experts/lib/localize';

interface ChatToolbarProps {
  title: string;
  expert: ConversationExpertSummary | null | undefined;
  className?: string;
  actions?: ReactNode;
}

export function ChatToolbar({ title, expert, className, actions }: ChatToolbarProps) {
  const { t } = useTranslation();
  const isPlatform = expert?.ownership === 'platform';
  const display = expert ? localizeExpertDisplay(expert, t) : null;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-3.5 py-3 px-4 sm:px-6 border-b border-border shrink-0',
        className,
      )}
      data-testid="chat-toolbar"
    >
      <div className="flex flex-col justify-center gap-1 min-w-0">
        <h1 className="text-lg font-semibold truncate">{title}</h1>
        {expert && display && (
          <div className="flex items-center gap-2 min-w-0">
            {expert.icon_url ? (
              <img
                src={expert.icon_url}
                alt=""
                className="size-5 rounded-full object-cover"
              />
            ) : (
              <div className="size-5 rounded-full bg-muted flex items-center justify-center text-[10px] font-semibold text-muted-foreground">
                {display.name.charAt(0).toUpperCase()}
              </div>
            )}
            <span className="text-xs text-muted-foreground truncate">{display.name}</span>
            {isPlatform && (
              <Badge variant="secondary" appearance="light" size="sm">
                {t('experts.platformBadge')}
              </Badge>
            )}
          </div>
        )}
      </div>
      {actions ? <div className="flex items-center gap-2.5">{actions}</div> : null}
    </div>
  );
}
