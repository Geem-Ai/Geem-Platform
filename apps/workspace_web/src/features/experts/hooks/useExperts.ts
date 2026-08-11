import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { listExperts } from '@/services/api/experts';
import { queryKeys } from '@/services/api/query-keys';

export function useExperts() {
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  return useQuery({
    queryKey: queryKeys.experts(workspaceId),
    queryFn: () => listExperts(),
    enabled: Boolean(workspaceId),
  });
}
