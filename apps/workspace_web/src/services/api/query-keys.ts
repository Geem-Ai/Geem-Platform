/**
 * Frontend tenant-isolation rule (Phase 1B+):
 * Workspace-owned React Query keys MUST include workspace identity:
 *   ['workspace', workspaceId, ...]
 * On workspace switch / logout: removeQueries for previous workspace keys.
 */

export function workspaceQueryKey(
  workspaceId: string,
  ...parts: readonly unknown[]
): readonly unknown[] {
  return ['workspace', workspaceId, ...parts];
}

export const queryKeys = {
  me: ['auth', 'me'] as const,
  workspaces: ['workspaces'] as const,
  members: (workspaceId: string) => workspaceQueryKey(workspaceId, 'members'),
  workspace: (workspaceId: string) => workspaceQueryKey(workspaceId, 'detail'),
  documents: (workspaceId: string) => workspaceQueryKey(workspaceId, 'documents'),
  document: (workspaceId: string, documentId: string) =>
    workspaceQueryKey(workspaceId, 'documents', documentId),
  experts: (workspaceId: string) => workspaceQueryKey(workspaceId, 'experts'),
  expert: (workspaceId: string, expertId: string) =>
    workspaceQueryKey(workspaceId, 'experts', expertId),
  expertKnowledge: (workspaceId: string, expertId: string) =>
    workspaceQueryKey(workspaceId, 'experts', expertId, 'knowledge'),
  conversations: (workspaceId: string) =>
    workspaceQueryKey(workspaceId, 'conversations'),
  conversation: (workspaceId: string, conversationId: string) =>
    workspaceQueryKey(workspaceId, 'conversations', conversationId),
  conversationMessages: (workspaceId: string, conversationId: string) =>
    workspaceQueryKey(workspaceId, 'conversations', conversationId, 'messages'),
  usageSummary: (workspaceId: string) =>
    workspaceQueryKey(workspaceId, 'usage', 'summary'),
  usageHistory: (
    workspaceId: string,
    params?: {
      limit: number;
      offset: number;
      kind?: string;
      from?: string;
      to?: string;
    },
  ) =>
    params
      ? workspaceQueryKey(workspaceId, 'usage', 'history', params)
      : workspaceQueryKey(workspaceId, 'usage', 'history'),
  subscription: (workspaceId: string) =>
    workspaceQueryKey(workspaceId, 'subscription'),
};
