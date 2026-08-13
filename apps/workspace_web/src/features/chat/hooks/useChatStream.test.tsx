import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ApiError } from '@/services/api/errors';

const streamMock = vi.fn();
const retryMock = vi.fn();

vi.mock('@/services/api/conversations', () => ({
  streamConversationMessage: (...args: unknown[]) => streamMock(...args),
  retryConversationMessageStream: (...args: unknown[]) => retryMock(...args),
}));

import { useChatStream, titlePollConfig, shouldRetainUnpersistedTurn } from './useChatStream';
import type { ChatUiMessage } from '../types';
import {
  clearActiveChatTurn,
  ensureActiveChatTurn,
  getActiveChatTurn,
} from '../lib/activeChatTurn';
import {
  clearPendingChatMessage,
  peekPendingChatMessage,
  setPendingChatMessage,
} from '../lib/pendingChatMessage';

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

describe('useChatStream', () => {
  const defaultTitlePollDelays = titlePollConfig.delaysMs;

  beforeEach(() => {
    streamMock.mockReset();
    retryMock.mockReset();
    titlePollConfig.delaysMs = [];
    clearActiveChatTurn('c1');
    clearPendingChatMessage('c1');
  });

  afterEach(() => {
    titlePollConfig.delaysMs = defaultTitlePollDelays;
    clearActiveChatTurn('c1');
    clearPendingChatMessage('c1');
  });

  it('optimistically appends user + assistant and reconciles IDs without duplicates', async () => {
    streamMock.mockImplementation(
      async (
        _id: string,
        _content: string,
        handlers: {
          onEvent?: (event: string, data: unknown) => void;
        },
      ) => {
        handlers.onEvent?.('message_start', {
          conversation_id: 'c1',
          user_message_id: 'u-server',
          assistant_message_id: 'a-server',
        });
        handlers.onEvent?.('token', { text: 'Hel' });
        handlers.onEvent?.('token', { text: 'lo' });
        handlers.onEvent?.('final', {
          answer: 'Hello',
          citations: [
            {
              chunk_id: 'ch1',
              document_id: 'd1',
              document_title: 'Doc',
              page: 1,
              snippet: 'snip',
            },
          ],
          assistant_message_id: 'a-server',
          user_message_id: 'u-server',
          status: 'completed',
        });
        handlers.onEvent?.('message_complete', {
          assistant_message_id: 'a-server',
          user_message_id: 'u-server',
          status: 'completed',
          citations: [
            {
              chunk_id: 'ch1',
              document_id: 'd1',
              document_title: 'Doc',
              page: 1,
              snippet: 'snip',
            },
          ],
        });
      },
    );

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: [],
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.send('Hi there');
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    const users = result.current.messages.filter((m) => m.role === 'user');
    const assistants = result.current.messages.filter((m) => m.role === 'assistant');
    expect(users).toHaveLength(1);
    expect(assistants).toHaveLength(1);
    expect(users[0]?.id).toBe('u-server');
    expect(users[0]?.content).toBe('Hi there');
    expect(assistants[0]?.id).toBe('a-server');
    expect(assistants[0]?.content).toBe('Hello');
    expect(assistants[0]?.citations).toHaveLength(1);
    expect(assistants[0]?.status).toBe('completed');
  });

  it('invokes AbortController and marks assistant cancelled', async () => {
    let capturedSignal: AbortSignal | undefined;
    let rejectStream: ((err: unknown) => void) | undefined;

    streamMock.mockImplementation(
      async (
        _id: string,
        _content: string,
        handlers: {
          onEvent?: (event: string, data: unknown) => void;
        },
        signal?: AbortSignal,
      ) => {
        capturedSignal = signal;
        handlers.onEvent?.('message_start', {
          conversation_id: 'c1',
          user_message_id: 'u1',
          assistant_message_id: 'a1',
        });
        handlers.onEvent?.('token', { text: 'partial' });
        await new Promise<void>((_resolve, reject) => {
          rejectStream = reject;
          signal?.addEventListener('abort', () => {
            reject(new ApiError('Request aborted', { status: 0, code: 'aborted' }));
          });
        });
      },
    );

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: [],
        }),
      { wrapper: createWrapper() },
    );

    let sendPromise!: Promise<void>;
    act(() => {
      sendPromise = result.current.send('Question');
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(true);
      expect(capturedSignal).toBeTruthy();
    });

    act(() => {
      result.current.abort();
    });

    await act(async () => {
      await sendPromise;
    });

    expect(capturedSignal?.aborted).toBe(true);
    expect(rejectStream).toBeTypeOf('function');
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant?.status).toBe('cancelled');
    expect(assistant?.content).toContain('partial');
    expect(result.current.isStreaming).toBe(false);
  });

  it('retry streams into the failed assistant without duplicating the user message', async () => {
    retryMock.mockImplementation(
      async (
        _cid: string,
        _aid: string,
        handlers: { onEvent?: (event: string, data: unknown) => void },
      ) => {
        handlers.onEvent?.('message_start', {
          conversation_id: 'c1',
          user_message_id: 'u1',
          assistant_message_id: 'a1',
        });
        handlers.onEvent?.('token', { text: 'Retried' });
        handlers.onEvent?.('final', {
          answer: 'Retried',
          citations: [],
          assistant_message_id: 'a1',
          user_message_id: 'u1',
          status: 'completed',
        });
      },
    );

    const seed = [
      {
        id: 'u1',
        role: 'user' as const,
        content: 'Original question',
        citations: [],
        status: 'completed' as const,
        created_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'a1',
        role: 'assistant' as const,
        content: '',
        citations: [],
        status: 'failed' as const,
        created_at: '2026-01-01T00:00:01Z',
        errorMessage: 'Unable to complete',
      },
    ];

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: seed,
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.retry('a1');
    });

    expect(result.current.messages.filter((m) => m.role === 'user')).toHaveLength(1);
    expect(result.current.messages.filter((m) => m.role === 'assistant')).toHaveLength(1);
    expect(result.current.messages.find((m) => m.role === 'assistant')?.content).toBe(
      'Retried',
    );
    expect(retryMock).toHaveBeenCalledWith(
      'c1',
      'a1',
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });

  it('starts the network stream after an optimistic first-message seed', async () => {
    streamMock.mockImplementation(async () => undefined);
    ensureActiveChatTurn('c1', 'First from starter');

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: [],
        }),
      { wrapper: createWrapper() },
    );

    expect(result.current.isStreaming).toBe(true);

    await act(async () => {
      await result.current.send('First from starter');
    });

    expect(streamMock).toHaveBeenCalledWith(
      'c1',
      'First from starter',
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });

  it('clears pending handoff before active turn so title invalidation cannot re-seed thinking', async () => {
    setPendingChatMessage('c1', 'Hello laws');
    ensureActiveChatTurn('c1', 'Hello laws');

    streamMock.mockImplementation(
      async (
        _id: string,
        _content: string,
        handlers: { onEvent?: (event: string, data: unknown) => void },
      ) => {
        handlers.onEvent?.('message_start', {
          conversation_id: 'c1',
          user_message_id: 'u1',
          assistant_message_id: 'a1',
        });
        handlers.onEvent?.('token', { text: 'Final answer' });
        handlers.onEvent?.('final', {
          answer: 'Final answer',
          citations: [],
          assistant_message_id: 'a1',
          user_message_id: 'u1',
          status: 'completed',
        });
        handlers.onEvent?.('message_complete', {
          assistant_message_id: 'a1',
          user_message_id: 'u1',
          status: 'completed',
          citations: [],
        });
      },
    );

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: [],
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.send('Hello laws');
    });

    expect(peekPendingChatMessage('c1')).toBeNull();
    expect(getActiveChatTurn('c1')).toBeNull();
    expect(result.current.isStreaming).toBe(false);
    expect(
      result.current.messages.find((m) => m.role === 'assistant')?.content,
    ).toBe('Final answer');

    // Simulate a mistaken late seed (old render-path bug): without pending,
    // ChatPage will not recreate a thinking card after title poll.
    expect(peekPendingChatMessage('c1')).toBeNull();
  });

  it('surfaces quota_exceeded instead of a generic generation failure', async () => {
    streamMock.mockImplementation(
      async (
        _id: string,
        _content: string,
        handlers: {
          onEvent?: (event: string, data: unknown) => void;
          onError?: (message: string, code?: string) => void;
        },
      ) => {
        handlers.onEvent?.('error', {
          error: 'quota_exceeded',
          message: 'AI quota exceeded',
        });
        handlers.onError?.('AI quota exceeded', 'quota_exceeded');
        throw new ApiError('AI quota exceeded', {
          status: 0,
          code: 'quota_exceeded',
        });
      },
    );

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: [],
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.send('Need an answer');
    });

    expect(result.current.errorCode).toBe('quota_exceeded');
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant?.status).toBe('failed');
    expect(assistant?.errorCode).toBe('quota_exceeded');
    expect(assistant?.content).toBe('');
    expect(result.current.messages.find((m) => m.role === 'user')?.content).toBe(
      'Need an answer',
    );
  });

  it('keeps an unpersisted quota-failed turn when prior server history refetches', async () => {
    const prior: ChatUiMessage[] = [
      {
        id: 'u-old',
        role: 'user',
        content: 'Earlier question',
        citations: [],
        status: 'completed',
        created_at: '2026-08-01T00:00:00Z',
      },
      {
        id: 'a-old',
        role: 'assistant',
        content: 'Earlier answer',
        citations: [],
        status: 'completed',
        created_at: '2026-08-01T00:00:01Z',
      },
    ];

    streamMock.mockImplementation(
      async (
        _id: string,
        _content: string,
        handlers: {
          onEvent?: (event: string, data: unknown) => void;
          onError?: (message: string, code?: string) => void;
        },
      ) => {
        handlers.onError?.('AI quota exceeded', 'quota_exceeded');
        throw new ApiError('AI quota exceeded', {
          status: 0,
          code: 'quota_exceeded',
        });
      },
    );

    const { result } = renderHook(
      () =>
        useChatStream({
          workspaceId: 'ws1',
          conversationId: 'c1',
          initialMessages: prior,
        }),
      { wrapper: createWrapper() },
    );

    await act(async () => {
      await result.current.send('Need an answer');
    });

    expect(shouldRetainUnpersistedTurn(result.current.messages)).toBe(true);
    expect(
      result.current.messages.find((m) => m.content === 'Earlier question'),
    ).toBeTruthy();
    expect(
      result.current.messages.find((m) => m.content === 'Need an answer'),
    ).toBeTruthy();
    const assistant = result.current.messages.find(
      (m) => m.role === 'assistant' && m.status === 'failed',
    );
    expect(assistant?.errorCode).toBe('quota_exceeded');
  });
});
