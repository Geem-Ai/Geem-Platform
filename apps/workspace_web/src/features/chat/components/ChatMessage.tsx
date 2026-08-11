import { useTranslation } from 'react-i18next';
import { RotateCcw } from 'lucide-react';
import {
  Avatar,
  AvatarFallback,
} from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { geemAvatarUrl } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { errorMessageKey } from '@/services/api/errors';
import type { ApiErrorCode } from '@/services/api/errors';
import { CitationList } from './CitationList';
import { MessageRenderer } from './MessageRenderer';
import { ThinkingStatus } from './ThinkingStatus';
import type { ChatUiMessage } from '../types';

interface ChatMessageProps {
  message: ChatUiMessage;
  userLabel?: string;
  userInitials?: string;
  isPlatformExpert?: boolean;
  isStreaming?: boolean;
  onRetry?: (assistantMessageId: string) => void;
  className?: string;
}

export function ChatMessage({
  message,
  userLabel,
  userInitials = 'U',
  isPlatformExpert = false,
  isStreaming = false,
  onRetry,
  className,
}: ChatMessageProps) {
  const { t } = useTranslation();
  const isUser = message.role === 'user';
  const failed =
    message.status === 'failed' || Boolean(message.errorMessage);
  const cancelled = message.status === 'cancelled';
  const showRetry =
    !isUser &&
    (failed || cancelled) &&
    onRetry &&
    !message.id.startsWith('client-');

  return (
    <div
      className={cn(
        'flex items-start gap-3 py-4',
        isUser && 'flex-row-reverse',
        className,
      )}
      data-testid={isUser ? 'chat-message-user' : 'chat-message-assistant'}
      data-message-id={message.id}
      data-status={message.status}
    >
      {isUser ? (
        <Avatar className="size-9 shrink-0">
          <AvatarFallback className="bg-primary/15 text-primary text-xs font-semibold">
            {userInitials}
          </AvatarFallback>
        </Avatar>
      ) : (
        <img
          src={geemAvatarUrl()}
          alt={t('app.name')}
          className="size-8 shrink-0 rounded-full object-cover bg-primary/10"
          data-testid="geem-assistant-avatar"
        />
      )}

      <div
        className={cn(
          'flex flex-col gap-1 flex-1 min-w-0',
          isUser && 'items-end',
        )}
      >
        <div
          className={cn(
            'rounded-2xl px-5 py-3.5 text-sm shadow-sm relative',
            isUser
              ? 'bg-primary text-primary-foreground max-w-[85%] rounded-ee-sm'
              : 'bg-muted/50 text-foreground max-w-[90%] rounded-es-sm',
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words leading-relaxed">
              {message.content}
            </p>
          ) : failed && !message.content ? (
            <p className="text-destructive" role="alert">
              {message.errorMessage || t('chat.responseFailed')}
            </p>
          ) : (
            <>
              {message.content ? (
                <MessageRenderer content={message.content} />
              ) : isStreaming ? (
                <>
                  <span className="sr-only" role="status" aria-live="polite">
                    {t('chat.thinking')}
                  </span>
                  <ThinkingStatus />
                </>
              ) : null}
              {isStreaming && message.content ? (
                <span
                  className="inline-block w-2 h-4 ms-1 bg-current animate-pulse align-middle"
                  aria-hidden
                />
              ) : null}
              {cancelled && !isStreaming && (
                <p className="text-xs text-muted-foreground mt-2 italic">
                  {t('chat.cancelled')}
                </p>
              )}
              {failed && message.content && (
                <p className="text-xs text-destructive mt-2" role="alert">
                  {message.errorMessage || t('chat.responseFailed')}
                </p>
              )}
              {!isStreaming && message.citations.length > 0 && (
                <CitationList
                  citations={message.citations}
                  isPlatform={isPlatformExpert}
                />
              )}
            </>
          )}

          {showRetry && (
            <div className="flex items-center gap-1 mt-3 pt-3 border-t border-border">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-muted-foreground hover:text-foreground"
                onClick={() => onRetry?.(message.id)}
              >
                <RotateCcw className="size-3.5" />
                {t('chat.retry')}
              </Button>
            </div>
          )}
        </div>

        {!isUser && (
          <span className="text-xs text-muted-foreground px-1">
            {userLabel ? null : t('app.name')}
          </span>
        )}
      </div>
    </div>
  );
}

/** Map API error code for toast/inline helpers outside the bubble. */
export function chatErrorLabel(
  t: (key: string) => string,
  code: ApiErrorCode | null,
  fallback?: string | null,
): string {
  if (code) return t(errorMessageKey(code));
  return fallback || t('chat.streamError');
}
