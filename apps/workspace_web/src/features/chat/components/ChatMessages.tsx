import { useTranslation } from 'react-i18next';
import { ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { ChatMessage } from './ChatMessage';
import { useStickToBottom } from '../hooks/useStickToBottom';
import type { ChatUiMessage } from '../types';

interface ChatMessagesProps {
  messages: ChatUiMessage[];
  userInitials?: string;
  isPlatformExpert?: boolean;
  streamingAssistantId?: string | null;
  onRetry?: (assistantMessageId: string) => void;
  isLoading?: boolean;
  className?: string;
}

export function ChatMessages({
  messages,
  userInitials,
  isPlatformExpert,
  streamingAssistantId,
  onRetry,
  isLoading,
  className,
}: ChatMessagesProps) {
  const { t } = useTranslation();
  const lastId = messages[messages.length - 1]?.id;
  const lastContent = messages[messages.length - 1]?.content;
  const { containerRef, bottomRef, showJump, onScroll, scrollToBottom } =
    useStickToBottom([messages.length, lastId, lastContent, streamingAssistantId]);

  if (isLoading) {
    return (
      <div
        className={cn('flex flex-1 items-center justify-center', className)}
        data-testid="chat-messages-loading"
      >
        <p className="text-sm text-muted-foreground">{t('chat.loadingHistory')}</p>
      </div>
    );
  }

  return (
    <div className={cn('relative flex-1 min-h-0', className)}>
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="flex flex-col h-full overflow-y-auto space-y-1 px-4 sm:px-6 py-4"
        data-testid="chat-messages"
      >
        {messages.map((message) => (
          <ChatMessage
            key={message.clientId ?? message.id}
            message={message}
            userInitials={userInitials}
            isPlatformExpert={isPlatformExpert}
            isStreaming={
              streamingAssistantId != null &&
              (message.id === streamingAssistantId ||
                message.clientId === streamingAssistantId ||
                (message.status === 'streaming' && message.role === 'assistant'))
            }
            onRetry={onRetry}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {showJump && (
        <div className="absolute bottom-3 inset-x-0 flex justify-center pointer-events-none">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="pointer-events-auto rounded-full shadow-md gap-1.5 bg-background"
            onClick={() => scrollToBottom('smooth')}
          >
            <ArrowDown className="size-3.5" />
            {t('chat.scrollToBottom')}
          </Button>
        </div>
      )}
    </div>
  );
}
