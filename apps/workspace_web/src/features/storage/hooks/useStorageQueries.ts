import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { queryKeys } from '@/services/api/query-keys';
import {
  deleteDocument,
  downloadDocumentFile,
  listDocuments,
  STORAGE_PAGE_SIZE,
} from '@/services/api/documents';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useStorageDocuments(params: {
  page: number;
  q: string;
  enabled?: boolean;
}) {
  const workspaceId = useWorkspaceId();
  const limit = STORAGE_PAGE_SIZE;
  const offset = Math.max(0, (params.page - 1) * limit);
  const q = params.q.trim() || undefined;
  return useQuery({
    queryKey: queryKeys.documents(workspaceId, { limit, offset, q: q ?? '' }),
    queryFn: () => listDocuments({ limit, offset, q }),
    enabled: Boolean(workspaceId) && (params.enabled ?? true),
  });
}

export function useDeleteStorageDocument() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.usageSummary(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.experts(workspaceId) }),
      ]);
    },
  });
}

export function useDownloadStorageDocument() {
  return useMutation({
    mutationFn: downloadDocumentFile,
  });
}
