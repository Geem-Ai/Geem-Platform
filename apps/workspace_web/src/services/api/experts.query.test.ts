import { beforeEach, describe, expect, it, vi } from 'vitest';

const streamSseMock = vi.fn((_path: string, body: unknown) => {
  void _path;
  (globalThis as { __capturedBody?: unknown }).__capturedBody = body;
  return Promise.resolve();
});

vi.mock('@/services/api/sse', () => ({
  streamSse: (...args: unknown[]) =>
    streamSseMock(args[0] as string, args[1]),
}));

describe('queryExpertStream body shape', () => {
  beforeEach(() => {
    streamSseMock.mockClear();
    delete (globalThis as { __capturedBody?: unknown }).__capturedBody;
  });

  it('sends only question and expert_id — no document_ids', async () => {
    const { queryExpertStream } = await import('./query');
    await queryExpertStream('hello', 'expert-123', {});

    const capturedBody = (globalThis as { __capturedBody?: unknown }).__capturedBody;
    expect(capturedBody).toEqual({
      question: 'hello',
      expert_id: 'expert-123',
    });
    expect(capturedBody).not.toHaveProperty('document_ids');
    expect(capturedBody).not.toHaveProperty('document_id');
  });
});
