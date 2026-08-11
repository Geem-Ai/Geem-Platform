import { useEffect, useMemo, useRef } from 'react';
import {
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { ChatComposer } from '../components/ChatComposer';
import { ChatMessages } from '../components/ChatMessages';
import { ChatToolbar } from '../components/ChatToolbar';
import {
  useConversation,
  useConversationMessages,
} from '../hooks/useConversation';
import { useChatStream } from '../hooks/useChatStream';
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

  // Survive React Strict Mode remounts for the starter → conversation handoff.
  const pendingStartedKey = useRef<string | null>(null);

  // First message from /chat starter — send once after mount.
  useEffect(() => {
    if (!conversationId || isStreaming) return;
    const state = location.state as ChatPendingLocationState | null;
    const pending = state?.pendingMessage?.trim();
    if (!pending) return;
    const key = `${conversationId}:${pending}`;
    if (pendingStartedKey.current === key) return;
    pendingStartedKey.current = key;
    void navigate(location.pathname, { replace: true, state: {} });
    void send(pending);
  }, [conversationId, isStreaming, location.pathname, location.state, navigate, send]);

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

  const loadingHistory =
    (conversationQuery.isLoading || messagesQuery.isLoading) &&
    messages.length === 0;

  return (
    <div
      className="flex flex-col h-[calc(100vh-var(--header-height-mobile)-3.5rem)] lg:h-[calc(100vh-2.5rem)]"
      data-testid="chat-page"
    >
      <Helmet>
        <title>
          {title} — {t('app.name')}
        </title>
      </Helmet>

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
        <div className="max-w-3xl mx-auto">
          <ChatComposer
            variant="compact"
            onSubmit={(q) => void send(q)}
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
