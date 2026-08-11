import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Expert } from '@/services/api/types';
import { canAskExpert } from '@/features/experts/lib/capabilities';
import { useExpertQueryStream } from '@/features/experts/hooks/useExpertQueryStream';
import { errorMessageKey } from '@/services/api/errors';
import { CitationList } from './CitationList';
import { Composer } from './Composer';
import { MessageRenderer } from './MessageRenderer';

interface ChatShellProps {
  expert: Expert;
  workspaceId: string;
}

export function ChatShell({ expert, workspaceId }: ChatShellProps) {
  const { t } = useTranslation();
  const {
    isStreaming,
    answer,
    citations,
    error,
    errorCode,
    insufficientContext,
    ask,
    clear,
    abort,
  } = useExpertQueryStream(workspaceId);

  /** Reset when the selected expert changes mid-session. */
  useEffect(() => {
    clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expert.id]);

  const isPlatform = expert.ownership === 'platform';
  const askEnabled = canAskExpert(expert.status);

  let askHint: string | null = null;
  if (!askEnabled) {
    if (expert.status === 'draft') askHint = t('chat.askDisabledDraft');
    else if (expert.status === 'processing') askHint = t('chat.askDisabledProcessing');
    else if (expert.status === 'failed') askHint = t('chat.askDisabledFailed');
    else if (expert.status === 'disabled') askHint = t('chat.askDisabled');
    else askHint = t('chat.askDisabled');
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border shrink-0">
        {expert.icon_url ? (
          <img src={expert.icon_url} alt={expert.name} className="size-7 rounded-full object-cover" />
        ) : (
          <div className="size-7 rounded-full bg-muted flex items-center justify-center text-xs font-semibold text-muted-foreground">
            {expert.name.charAt(0).toUpperCase()}
          </div>
        )}
        <div className="min-w-0">
          <span className="text-sm font-medium block truncate">{expert.name}</span>
          {isPlatform && (
            <span className="text-[11px] text-muted-foreground">{t('experts.platformBadge')}</span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
        {!answer && !isStreaming && !error && (
          <div className="flex h-full items-center justify-center text-center">
            <div className="space-y-2 max-w-sm">
              <p className="text-sm text-muted-foreground">
                {askHint ?? t('chat.askHint', { name: expert.name })}
              </p>
            </div>
          </div>
        )}

        {(answer || isStreaming) && (
          <div className="space-y-3">
            <MessageRenderer content={answer} />
            {isStreaming && (
              <span
                className="inline-block h-3 w-0.5 rounded-full bg-foreground animate-pulse"
                aria-live="polite"
                aria-label={t('chat.sending')}
              />
            )}
            {insufficientContext && !isStreaming && (
              <p className="text-xs text-muted-foreground italic">
                {t('chat.insufficientContext')}
              </p>
            )}
            {!isStreaming && citations.length > 0 && (
              <CitationList citations={citations} isPlatform={isPlatform} />
            )}
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {errorCode ? t(errorMessageKey(errorCode)) : t('chat.streamError')}
            {!errorCode && error ? ` — ${error}` : null}
          </p>
        )}
      </div>

      <div className="px-4 pb-4 shrink-0 space-y-2">
        {askHint && (
          <p className="text-xs text-muted-foreground">{askHint}</p>
        )}
        <Composer
          onSubmit={(q) => void ask(q, expert.id)}
          onStop={abort}
          disabled={!askEnabled}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}
