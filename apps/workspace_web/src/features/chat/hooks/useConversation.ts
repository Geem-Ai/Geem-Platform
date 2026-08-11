import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  getConversation,
  listConversationMessages,
} from '@/services/api/conversations';
import { queryKeys } from '@/services/api/query-keys';

export function useConversation(conversationId: string | undefined) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  return useQuery({
    queryKey: queryKeys.conversation(workspaceId, conversationId ?? ''),
    queryFn: () => getConversation(conversationId!),
    enabled: Boolean(workspaceId) && Boolean(conversationId),
  });
}

export function useConversationMessages(conversationId: string | undefined) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  return useQuery({
    queryKey: queryKeys.conversationMessages(workspaceId, conversationId ?? ''),
    queryFn: () => listConversationMessages(conversationId!, { limit: 500 }),
    enabled: Boolean(workspaceId) && Boolean(conversationId),
  });
}
