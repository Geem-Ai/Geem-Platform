import { describe, expect, it } from 'vitest';
import { queryKeys, workspaceQueryKey } from '@/services/api/query-keys';

describe('conversation query keys workspace isolation', () => {
  it('scopes conversation lists and details per workspace', () => {
    const a = queryKeys.conversations('ws-a');
    const b = queryKeys.conversations('ws-b');
    expect(a).not.toEqual(b);
    expect(a[0]).toBe('workspace');
    expect(a[1]).toBe('ws-a');
    expect(b[1]).toBe('ws-b');

    expect(queryKeys.conversation('ws-a', 'c1')).toEqual(
      workspaceQueryKey('ws-a', 'conversations', 'c1'),
    );
    expect(queryKeys.conversationMessages('ws-a', 'c1')).toEqual(
      workspaceQueryKey('ws-a', 'conversations', 'c1', 'messages'),
    );
    expect(queryKeys.conversation('ws-a', 'c1')).not.toEqual(
      queryKeys.conversation('ws-b', 'c1'),
    );
  });
});
