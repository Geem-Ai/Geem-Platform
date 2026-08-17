import { useEffect, useMemo } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { toast } from 'sonner';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey, isQuotaErrorCode } from '@/services/api/errors';
import { QuotaAlert } from '@/features/usage/components/QuotaAlert';
import { ChatComposer } from '../components/ChatComposer';
import { ChatMessages } from '../components/ChatMessages';
import { ChatToolbar } from '../components/ChatToolbar';
import {
  useConversation,
  useConversationMessages,
} from '../hooks/useConversation';
import { useChatStream } from '../hooks/useChatStream';
import { ensureActiveChatTurn, getActiveChatTurn } from '../lib/activeChatTurn';
import {
  beginPendingChatSend,
  clearPendingChatMessage,
  endPendingChatSend,
  peekPendingChatMessage,
  setPendingChatMessage,
} from '../lib/pendingChatMessage';
import { toChatUiMessage } from '../types';
import {
  useCurrentUserInitials,
  type ChatPendingLocationState,
} from './ChatStartPage';

export function ChatPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { conversationId } = useParams<{ conversationId: string }>();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';
  const userInitials = useCurrentUserInitials();

  const conversationQuery = useConversation(conversationId);
  const messagesQuery = useConversationMessages(conversationId);

  const initialMessages = useMemo(
    () => (messagesQuery.data ?? []).map(toChatUiMessage),
    [messagesQuery.data],
  );

  const {
    messages,
    isStreaming,
    error,
    errorCode,
    send,
    retry,
    abort,
  } = useChatStream({
    workspaceId,
    conversationId: conversationId ?? '',
    initialMessages,
  });

  // First message from /chat starter — send once (survives Strict Mode remount).
  // Seed the optimistic turn only here (and in ChatStartPage before navigate).
  // Never re-seed during render: after stream finally clears the active turn,
  // a lingering pending message would recreate an empty "thinking" card and
  // title/cache invalidation would look like it wiped the answer.
  useEffect(() => {
    if (!conversationId) return;

    const fromState = (location.state as ChatPendingLocationState | null)
      ?.pendingMessage;
    if (fromState) {
      const payload =
        typeof fromState === 'string'
          ? { content: fromState.trim() }
          : fromState;
      if (payload.content?.trim() || payload.attachmentId) {
        setPendingChatMessage(conversationId, payload);
      }
      // Clear router state so refresh/back doesn't re-send; storage keeps the handoff.
      void navigate(location.pathname, { replace: true, state: {} });
    }

    const pending = peekPendingChatMessage(conversationId);
    if (!pending) return;
    if (!pending.content.trim() && !pending.attachmentId) return;
    if (!beginPendingChatSend(conversationId)) return;

    const attachments =
      pending.attachmentId && pending.attachmentMeta
        ? [
            {
              id: pending.attachmentId,
              filename: pending.attachmentMeta.filename,
              mime_type: pending.attachmentMeta.mimeType,
              byte_size: pending.attachmentMeta.byteSize ?? 0,
            },
          ]
        : undefined;

    ensureActiveChatTurn(conversationId, pending.content, {
      attachmentId: pending.attachmentId,
      attachments,
    });

    void send(pending.content, {
      attachmentId: pending.attachmentId,
      attachmentMeta: pending.attachmentMeta,
    })
      .then(() => {
        clearPendingChatMessage(conversationId);
      })
      .finally(() => {
        endPendingChatSend(conversationId);
      });
  }, [
    conversationId,
    location.pathname,
    location.state,
    navigate,
    send,
  ]);

  // Workspace switch / inaccessible conversation → back to new chat.
  useEffect(() => {
    if (!conversationQuery.isError) return;
    const err = conversationQuery.error;
    if (err instanceof ApiError && (err.status === 404 || err.code === 'conversation_not_found' || err.code === 'not_found')) {
      toast.error(t('errors.conversationNotFound'));
      void navigate('/chat', { replace: true });
      return;
    }
    if (err instanceof ApiError && (err.status === 403 || err.code === 'forbidden')) {
      toast.error(t(errorMessageKey(err.code)));
      void navigate('/chat', { replace: true });
    }
  }, [conversationQuery.error, conversationQuery.isError, navigate, t]);

  // If conversation belongs to another workspace after switch, leave.
  useEffect(() => {
    const conv = conversationQuery.data;
    if (!conv || !workspaceId) return;
    if (conv.workspace_id !== workspaceId) {
      void navigate('/chat', { replace: true });
    }
  }, [conversationQuery.data, navigate, workspaceId]);

  useEffect(() => {
    if (!error || isStreaming) return;
    if (errorCode) {
      toast.error(t(errorMessageKey(errorCode)));
    }
  }, [error, errorCode, isStreaming, t]);

  const conversation = conversationQuery.data;
  const title =
    conversation?.title?.trim() || t('chat.untitled');
  const isPlatform = conversation?.expert?.ownership === 'platform';

  const streamingAssistantId = isStreaming
    ? messages.find((m) => m.role === 'assistant' && m.status === 'streaming')
        ?.clientId ??
      messages.find((m) => m.role === 'assistant' && m.status === 'streaming')?.id
    : null;

  const hasPendingFirstMessage = Boolean(
    conversationId &&
      (peekPendingChatMessage(conversationId) ||
        getActiveChatTurn(conversationId)?.isStreaming),
  );

  const loadingHistory =
    (conversationQuery.isLoading || messagesQuery.isLoading) &&
    messages.length === 0 &&
    !hasPendingFirstMessage &&
    !isStreaming;

  return (
    <div
      className="flex flex-col h-[calc(100vh-var(--header-height-mobile)-3.5rem)] lg:h-[calc(100vh-2.5rem)]"
      data-testid="chat-page"
    >
      <DocumentTitle title={title} />

      <ChatToolbar title={title} expert={conversation?.expert} />

      <ChatMessages
        messages={messages}
        userInitials={userInitials}
        isPlatformExpert={isPlatform}
        streamingAssistantId={streamingAssistantId}
        onRetry={(id) => void retry(id)}
        isLoading={loadingHistory}
        className="flex-1"
      />

      <div className="p-4 pb-6 shrink-0">
        <div className="max-w-3xl mx-auto space-y-3">
          {errorCode && isQuotaErrorCode(errorCode) ? (
            <QuotaAlert code={errorCode} />
          ) : null}
          <ChatComposer
            variant="compact"
            onSubmit={(q, opts) => void send(q, opts)}
            onStop={abort}
            isStreaming={isStreaming}
            disabled={!conversationId || conversationQuery.isError}
            autoFocus
          />
        </div>
      </div>
    </div>
  );
}
