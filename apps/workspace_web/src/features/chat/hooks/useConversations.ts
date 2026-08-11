import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { listConversations } from '@/services/api/conversations';
import { queryKeys } from '@/services/api/query-keys';

export function useConversations() {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  return useQuery({
    queryKey: queryKeys.conversations(workspaceId),
    queryFn: () => listConversations({ limit: 100 }),
    enabled: Boolean(workspaceId),
  });
}
