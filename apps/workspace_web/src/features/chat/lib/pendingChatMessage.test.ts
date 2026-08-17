import { afterEach, describe, expect, it } from 'vitest';
import {
  beginPendingChatSend,
  clearPendingChatMessage,
  endPendingChatSend,
  peekPendingChatMessage,
  setPendingChatMessage,
} from './pendingChatMessage';

describe('pendingChatMessage', () => {
  afterEach(() => {
    clearPendingChatMessage('c1');
    clearPendingChatMessage('c2');
  });

  it('stores and peeks a pending first message', () => {
    setPendingChatMessage('c1', '  Hello laws  ');
    expect(peekPendingChatMessage('c1')).toEqual({ content: 'Hello laws' });
  });

  it('guards concurrent sends across remounts', () => {
    setPendingChatMessage('c1', 'Q');
    expect(beginPendingChatSend('c1')).toBe(true);
    expect(beginPendingChatSend('c1')).toBe(false);
    endPendingChatSend('c1');
    expect(beginPendingChatSend('c1')).toBe(true);
    clearPendingChatMessage('c1');
  });

  it('stores attachment payload for starter handoff', () => {
    setPendingChatMessage('c2', {
      content: '',
      attachmentId: 'att-1',
      attachmentMeta: {
        filename: 'shot.png',
        mimeType: 'image/png',
        byteSize: 12,
      },
    });
    expect(peekPendingChatMessage('c2')).toEqual({
      content: '',
      attachmentId: 'att-1',
      attachmentMeta: {
        filename: 'shot.png',
        mimeType: 'image/png',
        byteSize: 12,
      },
    });
  });

  it('clear removes storage and in-flight lock', () => {
    setPendingChatMessage('c1', 'Q');
    expect(beginPendingChatSend('c1')).toBe(true);
    clearPendingChatMessage('c1');
    expect(peekPendingChatMessage('c1')).toBeNull();
    expect(beginPendingChatSend('c1')).toBe(true);
    endPendingChatSend('c1');
    clearPendingChatMessage('c1');
  });
});
