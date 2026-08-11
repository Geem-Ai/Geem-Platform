import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import {
  retryConversationMessageStream,
  streamConversationMessage,
} from '@/services/api/conversations';
import { ApiError, type ApiErrorCode } from '@/services/api/errors';
import { queryKeys } from '@/services/api/query-keys';
import type {
  ChatFinalEvent,
  ChatMessageCompleteEvent,
  ChatMessageStartEvent,
  ChatStreamErrorEvent,
  ChatTitleEvent,
  Citation,
  Conversation,
} from '@/services/api/types';
import { type ChatUiMessage } from '../types';
import {
  clearActiveChatTurn,
  buildOptimisticTurnMessages,
  getActiveChatTurn,
  patchActiveChatTurn,
  publishActiveChatTurn,
  subscribeActiveChatTurn,
} from '../lib/activeChatTurn';

const EMPTY_MESSAGES: ChatUiMessage[] = [];

/** Soft-poll delays while a background LLM title job commits. Mutable for tests. */
export const titlePollConfig: { delaysMs: number[] } = {
  delaysMs: [800, 1600, 2800, 4500],
};

function textFromPayload(data: unknown): string {
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (typeof obj.text === 'string') return obj.text;
    if (typeof obj.token === 'string') return obj.token;
  }
  return '';
}

function asCitations(value: unknown): Citation[] {
  return Array.isArray(value) ? (value as Citation[]) : [];
}

function mapApiErrorCode(err: unknown): ApiErrorCode {
  if (err instanceof ApiError) return err.code;
  return 'unknown';
}

async function pollForConversationTitle(
  queryClient: QueryClient,
  workspaceId: string,
  conversationId: string,
  isCancelled: () => boolean,
): Promise<void> {
  for (const delay of titlePollConfig.delaysMs) {
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    if (isCancelled()) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversation(workspaceId, conversationId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversations(workspaceId),
      }),
    ]);
    if (isCancelled()) return;
    const conv = queryClient.getQueryData<Conversation>(
      queryKeys.conversation(workspaceId, conversationId),
    );
    if (conv?.title?.trim()) return;
  }
}

export type UseChatStreamOptions = {
  workspaceId: string;
  conversationId: string;
  /** Seed from persisted history; replaced when server history reloads. */
  initialMessages?: ChatUiMessage[];
};

export function useChatStream({
  workspaceId,
  conversationId,
  initialMessages = EMPTY_MESSAGES,
}: UseChatStreamOptions) {
  const queryClient = useQueryClient();
  const seeded = getActiveChatTurn(conversationId);
  const [messages, setMessagesState] = useState<ChatUiMessage[]>(
    () => seeded?.messages ?? initialMessages,
  );
  const [isStreaming, setIsStreamingState] = useState(
    () => seeded?.isStreaming ?? false,
  );
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<ApiErrorCode | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef(conversationId);
  const messagesRef = useRef(messages);
  const isStreamingRef = useRef(isStreaming);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    isStreamingRef.current = isStreaming;
  }, [isStreaming]);

  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  /** Keep Strict Mode remounts in sync with an in-flight turn. */
  useEffect(() => {
    return subscribeActiveChatTurn(() => {
      const turn = getActiveChatTurn(conversationIdRef.current);
      if (!turn) return;
      // External store is source of truth while a turn is published.
      setMessagesState(turn.messages);
      setIsStreamingState(turn.isStreaming);
      messagesRef.current = turn.messages;
      isStreamingRef.current = turn.isStreaming;
    });
  }, []);

  const setMessages = useCallback(
    (update: ChatUiMessage[] | ((prev: ChatUiMessage[]) => ChatUiMessage[])) => {
      const prev = messagesRef.current;
      const next = typeof update === 'function' ? update(prev) : update;
      messagesRef.current = next;
      if (getActiveChatTurn(conversationId)) {
        patchActiveChatTurn(conversationId, {
          messages: next,
          isStreaming: isStreamingRef.current,
        });
      }
      setMessagesState(next);
    },
    [conversationId],
  );

  const setIsStreaming = useCallback(
    (next: boolean) => {
      isStreamingRef.current = next;
      setIsStreamingState(next);
      if (getActiveChatTurn(conversationId)) {
        patchActiveChatTurn(conversationId, {
          isStreaming: next,
          messages: messagesRef.current,
        });
      }
    },
    [conversationId],
  );

  /** Sync when persisted history arrives / changes (e.g. after reload). */
  const historyFingerprint = initialMessages
    .map((m) => `${m.id}:${m.status}:${m.created_at}:${m.content.length}:${m.citations.length}`)
    .join('|');

  useEffect(() => {
    if (isStreaming) return;
    if (getActiveChatTurn(conversationId)?.isStreaming) return;
    // Avoid wiping optimistic/local transcript when the messages query is still empty
    // (common right after abort/send before refetch settles).
    if (initialMessages.length === 0 && messagesRef.current.length > 0) return;
    setMessagesState(initialMessages);
    // fingerprint captures identity/content of server history; avoid depending on array identity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyFingerprint, isStreaming, conversationId]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const invalidateConversationCaches = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversation(workspaceId, conversationId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversationMessages(workspaceId, conversationId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversations(workspaceId),
      }),
    ]);
  }, [conversationId, queryClient, workspaceId]);

  /**
   * Abort + reset only when workspace/conversation identity actually changes.
   * Do not abort in effect cleanups — React Strict Mode remounts would cancel the
   * first-message stream and leave the title stuck on "New conversation".
   */
  const prevScopeRef = useRef<{
    workspaceId: string;
    conversationId: string;
  } | null>(null);
  useEffect(() => {
    const prev = prevScopeRef.current;
    prevScopeRef.current = { workspaceId, conversationId };
    if (prev === null) return;
    if (
      prev.workspaceId === workspaceId &&
      prev.conversationId === conversationId
    ) {
      return;
    }
    abort();
    clearActiveChatTurn(prev.conversationId);
    setIsStreaming(false);
    setError(null);
    setErrorCode(null);
    const nextSeed = getActiveChatTurn(conversationId);
    setMessagesState(nextSeed?.messages ?? initialMessages);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- scope identity only
  }, [workspaceId, conversationId, abort]);

  const handleStreamEvents = useCallback(
    (
      event: string,
      data: unknown,
      ctx: {
        userClientId: string;
        assistantClientId: string;
        accumulate: { text: string };
      },
    ) => {
      if (conversationIdRef.current !== conversationId) return;

      if (event === 'message_start') {
        const payload = data as ChatMessageStartEvent;
        setMessages((prev) =>
          prev.map((m) => {
            if (m.clientId === ctx.userClientId || m.id === ctx.userClientId) {
              return {
                ...m,
                id: payload.user_message_id,
                clientId: ctx.userClientId,
                status: 'completed',
              };
            }
            if (
              m.clientId === ctx.assistantClientId ||
              m.id === ctx.assistantClientId
            ) {
              return {
                ...m,
                id: payload.assistant_message_id,
                clientId: ctx.assistantClientId,
                status: 'streaming',
              };
            }
            return m;
          }),
        );
        if (payload.title) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.conversations(workspaceId),
          });
          void queryClient.invalidateQueries({
            queryKey: queryKeys.conversation(workspaceId, conversationId),
          });
        }
        return;
      }

      if (event === 'title') {
        const payload = data as ChatTitleEvent;
        if (payload.title?.trim()) {
          queryClient.setQueryData(
            queryKeys.conversation(workspaceId, conversationId),
            (prev: { title?: string | null } | undefined) =>
              prev ? { ...prev, title: payload.title } : prev,
          );
          void queryClient.invalidateQueries({
            queryKey: queryKeys.conversations(workspaceId),
          });
          void queryClient.invalidateQueries({
            queryKey: queryKeys.conversation(workspaceId, conversationId),
          });
        }
        return;
      }

      if (event === 'token' || event === 'message') {
        ctx.accumulate.text += textFromPayload(data);
        const next = ctx.accumulate.text;
        setMessages((prev) =>
          prev.map((m) =>
            m.clientId === ctx.assistantClientId || m.id === ctx.assistantClientId
              ? { ...m, content: next, status: 'streaming' }
              : m,
          ),
        );
        return;
      }

      if (event === 'replace') {
        ctx.accumulate.text = textFromPayload(data);
        const next = ctx.accumulate.text;
        setMessages((prev) =>
          prev.map((m) =>
            m.clientId === ctx.assistantClientId || m.id === ctx.assistantClientId
              ? { ...m, content: next, status: 'streaming' }
              : m,
          ),
        );
        return;
      }

      if (event === 'final' || event === 'message_complete') {
        const payload = data as ChatFinalEvent & ChatMessageCompleteEvent;
        if (typeof payload.answer === 'string') {
          ctx.accumulate.text = payload.answer;
        }
        const citations = asCitations(payload.citations);
        const status = payload.status ?? 'completed';
        setMessages((prev) =>
          prev.map((m) => {
            if (
              m.clientId === ctx.assistantClientId ||
              m.id === ctx.assistantClientId ||
              (payload.assistant_message_id && m.id === payload.assistant_message_id)
            ) {
              return {
                ...m,
                id: payload.assistant_message_id ?? m.id,
                content: ctx.accumulate.text,
                citations,
                status,
                errorMessage: null,
              };
            }
            if (
              payload.user_message_id &&
              (m.clientId === ctx.userClientId || m.id === ctx.userClientId)
            ) {
              return { ...m, id: payload.user_message_id, status: 'completed' };
            }
            return m;
          }),
        );
        return;
      }

      if (event === 'error') {
        const payload = (data ?? {}) as ChatStreamErrorEvent;
        setMessages((prev) =>
          prev.map((m) =>
            m.clientId === ctx.assistantClientId ||
            m.id === ctx.assistantClientId ||
            (payload.assistant_message_id && m.id === payload.assistant_message_id)
              ? {
                  ...m,
                  id: payload.assistant_message_id ?? m.id,
                  content: ctx.accumulate.text,
                  status: 'failed',
                  errorMessage: payload.message ?? 'Generation failed.',
                }
              : m,
          ),
        );
        setError(payload.message ?? 'Generation failed.');
        setErrorCode(
          typeof payload.error === 'string'
            ? (payload.error as ApiErrorCode)
            : 'generation_failed',
        );
      }
    },
    [conversationId, queryClient, setMessages, workspaceId],
  );

  const send = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;

      // Optimistic first-message seed (ChatStartPage → ChatPage) sets isStreaming
      // before the network call. Allow that resume; block only a real in-flight stream.
      const seeded = getActiveChatTurn(conversationId);
      const resumingOptimisticSeed =
        seeded !== null &&
        seeded.content === trimmed &&
        abortRef.current === null;
      if (isStreamingRef.current && !resumingOptimisticSeed) return;
      if (abortRef.current) return;

      abort();
      const controller = new AbortController();
      abortRef.current = controller;

      let userClientId: string;
      let assistantClientId: string;
      let nextMessages: ChatUiMessage[];

      if (seeded && seeded.content === trimmed) {
        userClientId = seeded.userClientId;
        assistantClientId = seeded.assistantClientId;
        nextMessages = seeded.messages;
      } else {
        const built = buildOptimisticTurnMessages(trimmed);
        userClientId = built.userClientId;
        assistantClientId = built.assistantClientId;
        nextMessages = [...messagesRef.current, ...built.messages];
        publishActiveChatTurn({
          conversationId,
          content: trimmed,
          messages: nextMessages,
          isStreaming: true,
          userClientId,
          assistantClientId,
        });
      }

      setMessagesState(nextMessages);
      messagesRef.current = nextMessages;
      setIsStreaming(true);
      setError(null);
      setErrorCode(null);

      const existing = queryClient.getQueryData<Conversation>(
        queryKeys.conversation(workspaceId, conversationId),
      );
      const expectTitle = !existing?.title?.trim();
      let turnCompleted = false;
      const accumulate = { text: '' };

      try {
        await streamConversationMessage(
          conversationId,
          trimmed,
          {
            onEvent(event, data) {
              if (event === 'message_complete' || event === 'final') {
                turnCompleted = true;
              }
              handleStreamEvents(event, data, {
                userClientId,
                assistantClientId,
                accumulate,
              });
            },
            onError(message) {
              setError(message);
              setErrorCode('generation_failed');
              setMessages((prev) =>
                prev.map((m) =>
                  m.clientId === assistantClientId || m.id === assistantClientId
                    ? {
                        ...m,
                        content: accumulate.text,
                        status: 'failed',
                        errorMessage: message,
                      }
                    : m,
                ),
              );
            },
          },
          controller.signal,
        );
      } catch (err) {
        if (err instanceof ApiError && err.code === 'aborted') {
          setMessages((prev) =>
            prev.map((m) =>
              m.clientId === assistantClientId ||
              (m.status === 'streaming' && m.role === 'assistant')
                ? {
                    ...m,
                    content: accumulate.text || m.content,
                    status: 'cancelled',
                  }
                : m,
            ),
          );
        } else {
          const message =
            err instanceof ApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : 'Unknown error';
          setError(message);
          setErrorCode(mapApiErrorCode(err));
          setMessages((prev) =>
            prev.map((m) =>
              m.clientId === assistantClientId || m.id === assistantClientId
                ? {
                    ...m,
                    content: accumulate.text,
                    status: 'failed',
                    errorMessage: message,
                  }
                : m,
            ),
          );
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
        clearActiveChatTurn(conversationId);
        await invalidateConversationCaches();
        if (expectTitle && turnCompleted) {
          const scopedId = conversationId;
          void pollForConversationTitle(
            queryClient,
            workspaceId,
            scopedId,
            () => conversationIdRef.current !== scopedId,
          );
        }
      }
    },
    [
      abort,
      conversationId,
      handleStreamEvents,
      invalidateConversationCaches,
      queryClient,
      setIsStreaming,
      setMessages,
      workspaceId,
    ],
  );

  const retry = useCallback(
    async (assistantMessageId: string) => {
      if (!assistantMessageId || isStreaming) return;
      if (assistantMessageId.startsWith('client-')) return;

      abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const userClientId = `retry-user-${assistantMessageId}`;
      const assistantClientId = `retry-assistant-${assistantMessageId}`;

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessageId
            ? {
                ...m,
                clientId: assistantClientId,
                content: '',
                citations: [],
                status: 'streaming',
                errorMessage: null,
              }
            : m,
        ),
      );
      setIsStreaming(true);
      setError(null);
      setErrorCode(null);

      const existing = queryClient.getQueryData<Conversation>(
        queryKeys.conversation(workspaceId, conversationId),
      );
      const expectTitle = !existing?.title?.trim();
      let turnCompleted = false;
      const accumulate = { text: '' };

      try {
        await retryConversationMessageStream(
          conversationId,
          assistantMessageId,
          {
            onEvent(event, data) {
              if (event === 'message_complete' || event === 'final') {
                turnCompleted = true;
              }
              handleStreamEvents(event, data, {
                userClientId,
                assistantClientId,
                accumulate,
              });
            },
            onError(message) {
              setError(message);
              setErrorCode('generation_failed');
              setMessages((prev) =>
                prev.map((m) =>
                  m.clientId === assistantClientId || m.id === assistantMessageId
                    ? {
                        ...m,
                        content: accumulate.text,
                        status: 'failed',
                        errorMessage: message,
                      }
                    : m,
                ),
              );
            },
          },
          controller.signal,
        );
      } catch (err) {
        if (err instanceof ApiError && err.code === 'aborted') {
          setMessages((prev) =>
            prev.map((m) =>
              m.clientId === assistantClientId || m.id === assistantMessageId
                ? {
                    ...m,
                    content: accumulate.text || m.content,
                    status: 'cancelled',
                  }
                : m,
            ),
          );
        } else {
          const message =
            err instanceof ApiError
              ? err.message
              : err instanceof Error
                ? err.message
                : 'Unknown error';
          setError(message);
          setErrorCode(mapApiErrorCode(err));
          setMessages((prev) =>
            prev.map((m) =>
              m.clientId === assistantClientId || m.id === assistantMessageId
                ? {
                    ...m,
                    content: accumulate.text,
                    status: 'failed',
                    errorMessage: message,
                  }
                : m,
            ),
          );
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
        await invalidateConversationCaches();
        if (expectTitle && turnCompleted) {
          const scopedId = conversationId;
          void pollForConversationTitle(
            queryClient,
            workspaceId,
            scopedId,
            () => conversationIdRef.current !== scopedId,
          );
        }
      }
    },
    [
      abort,
      conversationId,
      handleStreamEvents,
      invalidateConversationCaches,
      isStreaming,
      queryClient,
      workspaceId,
    ],
  );

  return {
    messages,
    isStreaming,
    error,
    errorCode,
    send,
    retry,
    abort,
    setMessages,
  };
}
