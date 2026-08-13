import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { keepPreviousIfSameWorkspace } from '@/features/billing/lib/query';
import { queryKeys } from '@/services/api/query-keys';
import {
  API_USAGE_HISTORY_PAGE_SIZE,
  createApiKey,
  getApiUsageHistory,
  getApiUsageSummary,
  listApiKeys,
  revokeApiKey,
  type ApiUsagePeriodKey,
  type CreateApiKeyInput,
} from '@/services/api/api-keys';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useApiKeys(options?: { enabled?: boolean }) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.apiKeys(workspaceId),
    queryFn: listApiKeys,
    enabled: Boolean(workspaceId) && (options?.enabled ?? true),
  });
}

export function useCreateApiKey() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateApiKeyInput) => createApiKey(input),
    gcTime: 0,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys(workspaceId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.apiUsageSummary(workspaceId),
      });
    },
  });
}

export function useRevokeApiKey() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (apiKeyId: string) => revokeApiKey(apiKeyId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys(workspaceId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.apiUsageSummary(workspaceId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.apiUsageHistory(workspaceId),
      });
    },
  });
}

export function useApiUsageSummary(period: ApiUsagePeriodKey = '30d') {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.apiUsageSummary(workspaceId, period),
    queryFn: () => getApiUsageSummary(period),
    enabled: Boolean(workspaceId),
  });
}

export function useApiUsageHistory(params?: {
  limit?: number;
  offset?: number;
  period?: ApiUsagePeriodKey;
  api_key_id?: string;
}) {
  const workspaceId = useWorkspaceId();
  const limit = params?.limit ?? API_USAGE_HISTORY_PAGE_SIZE;
  const offset = params?.offset ?? 0;
  const period = params?.period ?? '30d';
  const apiKeyId = params?.api_key_id;
  return useQuery({
    queryKey: queryKeys.apiUsageHistory(workspaceId, {
      limit,
      offset,
      period,
      api_key_id: apiKeyId,
    }),
    queryFn: () =>
      getApiUsageHistory({
        limit,
        offset,
        period,
        api_key_id: apiKeyId,
      }),
    enabled: Boolean(workspaceId),
    placeholderData: (previous, previousQuery) =>
      keepPreviousIfSameWorkspace(workspaceId, previous, previousQuery),
  });
}
