import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { listExpertDocuments } from '@/services/api/experts';
import { queryKeys } from '@/services/api/query-keys';
import { POLL_INTERVAL_MS, shouldPollKnowledge } from '../lib/polling';

export function useExpertKnowledge(expertId: string | undefined) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  return useQuery({
    queryKey: queryKeys.expertKnowledge(workspaceId, expertId ?? ''),
    queryFn: () => listExpertDocuments(expertId!),
    enabled: Boolean(workspaceId) && Boolean(expertId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return shouldPollKnowledge(data) ? POLL_INTERVAL_MS : false;
    },
  });
}
