import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { getExpert } from '@/services/api/experts';
import { queryKeys } from '@/services/api/query-keys';
import { POLL_INTERVAL_MS, shouldPollExpert } from '../lib/polling';

export function useExpert(expertId: string | undefined) {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  return useQuery({
    queryKey: queryKeys.expert(workspaceId, expertId ?? ''),
    queryFn: () => getExpert(expertId!),
    enabled: Boolean(workspaceId) && Boolean(expertId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return shouldPollExpert(data.status) ? POLL_INTERVAL_MS : false;
    },
  });
}
