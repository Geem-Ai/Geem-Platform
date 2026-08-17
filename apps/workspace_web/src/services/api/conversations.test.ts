import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestMock = vi.fn();
const streamSseMock = vi.fn(async () => undefined);

vi.mock('@/services/api/client', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...(args as [string, unknown?])),
}));

vi.mock('@/services/api/sse', () => ({
  streamSse: (...args: unknown[]) => streamSseMock(...(args as Parameters<typeof streamSseMock>)),
}));

import {
  createConversation,
  retryConversationMessageStream,
  streamConversationMessage,
} from '@/services/api/conversations';

describe('conversations API client', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    streamSseMock.mockReset();
    apiRequestMock.mockResolvedValue({
      id: 'conv-1',
      workspace_id: 'ws-1',
      expert_id: 'exp-9',
      user_id: 'u1',
      title: null,
      is_pinned: false,
      pinned_at: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      expert: null,
      last_message: null,
    });
  });

  it('creates conversation with expert_id only (no premature message)', async () => {
    await createConversation({ expert_id: 'exp-9' });
    expect(apiRequestMock).toHaveBeenCalledWith('/api/conversations', {
      method: 'POST',
      json: { expert_id: 'exp-9' },
    });
  });

  it('streams to the Phase 4B conversation message endpoint', async () => {
    await streamConversationMessage('c1', 'Hello', {});
    expect(streamSseMock).toHaveBeenCalledWith(
      '/api/conversations/c1/messages/stream',
      { content: 'Hello' },
      {},
      undefined,
    );
  });

  it('includes attachment_id when provided', async () => {
    await streamConversationMessage('c1', 'See file', {}, undefined, {
      attachmentId: 'att-9',
    });
    expect(streamSseMock).toHaveBeenCalledWith(
      '/api/conversations/c1/messages/stream',
      { content: 'See file', attachment_id: 'att-9' },
      {},
      undefined,
    );
  });

  it('retries via the assistant retry stream endpoint', async () => {
    await retryConversationMessageStream('c1', 'a1', {});
    expect(streamSseMock).toHaveBeenCalledWith(
      '/api/conversations/c1/messages/a1/retry/stream',
      {},
      {},
      undefined,
    );
  });
});
