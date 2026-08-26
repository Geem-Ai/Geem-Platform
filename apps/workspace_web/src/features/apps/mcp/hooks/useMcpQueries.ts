import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { invalidateAppsCache } from '@/features/apps/hooks/useAppsQueries';
import { queryKeys } from '@/services/api/query-keys';
import {
  createExpertMcpGrant,
  createExpertMcpSurfaceBinding,
  createMcpServer,
  decideMcpExternalApproval,
  deleteMcpServer,
  discoverMcpTools,
  getMcpAuthStatus,
  getMcpServer,
  getMcpUsage,
  listExpertMcpGrants,
  listExpertMcpSurfaceBindings,
  listMcpExternalApprovals,
  listMcpExternalDeliveries,
  listMcpServers,
  listMcpTools,
  reauthorizeMcpServer,
  reconcileMcpExternalDelivery,
  revokeExpertMcpGrant,
  revokeExpertMcpSurfaceBinding,
  startMcpOauth,
  updateMcpToolClassification,
  type McpGrantCreateInput,
  type McpServerCreateInput,
  type McpSurfaceBindingCreateInput,
  type McpToolClassification,
} from '@/services/api/mcp';

function useWorkspaceId(): string {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

async function invalidateMcp(
  queryClient: ReturnType<typeof useQueryClient>,
  workspaceId: string,
) {
  await Promise.all([
    queryClient.invalidateQueries({
      queryKey: queryKeys.mcpServers(workspaceId),
    }),
    queryClient.invalidateQueries({ queryKey: queryKeys.mcpUsage(workspaceId) }),
    invalidateAppsCache(queryClient, workspaceId, 'mcp-connectors'),
  ]);
}

export function useMcpUsage(enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.mcpUsage(workspaceId),
    queryFn: getMcpUsage,
    enabled: Boolean(workspaceId) && enabled,
  });
}

export function useMcpServers(
  params: { limit?: number; offset?: number } = {},
  enabled = true,
) {
  const workspaceId = useWorkspaceId();
  const scoped = { limit: params.limit ?? 100, offset: params.offset ?? 0 };
  return useQuery({
    queryKey: queryKeys.mcpServers(workspaceId, scoped),
    queryFn: () => listMcpServers(scoped),
    enabled: Boolean(workspaceId) && enabled,
  });
}

export function useMcpServer(connectionId: string | undefined, enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.mcpServer(workspaceId, connectionId ?? ''),
    queryFn: () => getMcpServer(connectionId!),
    enabled: Boolean(workspaceId) && Boolean(connectionId) && enabled,
  });
}

export function useMcpAuthStatus(
  connectionId: string | undefined,
  enabled = true,
) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.mcpServerAuthStatus(workspaceId, connectionId ?? ''),
    queryFn: () => getMcpAuthStatus(connectionId!),
    enabled: Boolean(workspaceId) && Boolean(connectionId) && enabled,
  });
}

export function useMcpTools(
  connectionId: string | undefined,
  params: { limit?: number; offset?: number } = {},
  enabled = true,
) {
  const workspaceId = useWorkspaceId();
  const scoped = { limit: params.limit ?? 50, offset: params.offset ?? 0 };
  return useQuery({
    queryKey: queryKeys.mcpTools(workspaceId, connectionId ?? '', scoped),
    queryFn: () => listMcpTools(connectionId!, scoped),
    enabled: Boolean(workspaceId) && Boolean(connectionId) && enabled,
  });
}

export function useCreateMcpServer() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: McpServerCreateInput) => createMcpServer(input),
    onSuccess: async () => invalidateMcp(queryClient, workspaceId),
  });
}

export function useDeleteMcpServer() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (connectionId: string) => deleteMcpServer(connectionId),
    onSuccess: async () => invalidateMcp(queryClient, workspaceId),
  });
}

export function useDiscoverMcpTools() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (connectionId: string) => discoverMcpTools(connectionId),
    onSuccess: async (_result, connectionId) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.mcpTools(workspaceId, connectionId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.mcpServer(workspaceId, connectionId),
        }),
      ]);
    },
  });
}

export function useUpdateMcpToolClassification(connectionId: string) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      toolId,
      classification,
    }: {
      toolId: string;
      classification: McpToolClassification;
    }) => updateMcpToolClassification(toolId, classification),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.mcpTools(workspaceId, connectionId),
      });
    },
  });
}

export function useStartMcpOauth() {
  return useMutation({
    mutationFn: ({
      connectionId,
      returnPath,
    }: {
      connectionId: string;
      returnPath?: string;
    }) => startMcpOauth(connectionId, returnPath),
  });
}

export function useReauthorizeMcpServer() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      connectionId,
      returnPath,
    }: {
      connectionId: string;
      returnPath?: string;
    }) =>
      reauthorizeMcpServer(connectionId, {
        return_path: returnPath ?? null,
      }),
    onSuccess: async (_result, { connectionId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.mcpServer(workspaceId, connectionId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.mcpServerAuthStatus(workspaceId, connectionId),
        }),
      ]);
    },
  });
}

export function useExpertMcpGrants(
  expertId: string | undefined,
  enabled = true,
) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.expertMcpGrants(workspaceId, expertId ?? ''),
    queryFn: () => listExpertMcpGrants(expertId!),
    enabled: Boolean(workspaceId) && Boolean(expertId) && enabled,
  });
}

export function useCreateExpertMcpGrant(expertId: string) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: McpGrantCreateInput) =>
      createExpertMcpGrant(expertId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertMcpGrants(workspaceId, expertId),
      });
    },
  });
}

export function useRevokeExpertMcpGrant(expertId: string) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (grantId: string) => revokeExpertMcpGrant(expertId, grantId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.expertMcpGrants(workspaceId, expertId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.expertMcpSurfaceBindings(workspaceId, expertId),
        }),
      ]);
    },
  });
}

export function useExpertMcpSurfaceBindings(
  expertId: string | undefined,
  enabled = true,
) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.expertMcpSurfaceBindings(workspaceId, expertId ?? ''),
    queryFn: () => listExpertMcpSurfaceBindings(expertId!),
    enabled: Boolean(workspaceId) && Boolean(expertId) && enabled,
  });
}

export function useCreateExpertMcpSurfaceBinding(expertId: string) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: McpSurfaceBindingCreateInput) =>
      createExpertMcpSurfaceBinding(expertId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertMcpSurfaceBindings(workspaceId, expertId),
      });
    },
  });
}

export function useRevokeExpertMcpSurfaceBinding(expertId: string) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bindingId: string) =>
      revokeExpertMcpSurfaceBinding(expertId, bindingId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertMcpSurfaceBindings(workspaceId, expertId),
      });
    },
  });
}

export function useMcpExternalApprovals(enabled = true) {
  const workspaceId = useWorkspaceId();
  const params = { limit: 100, offset: 0 };
  return useQuery({
    queryKey: queryKeys.mcpExternalApprovals(workspaceId, params),
    queryFn: () => listMcpExternalApprovals(params),
    enabled: Boolean(workspaceId) && enabled,
    refetchInterval: enabled ? 5_000 : false,
  });
}

export function useDecideMcpExternalApproval() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      approvalId,
      decision,
    }: {
      approvalId: string;
      decision: 'approve' | 'deny';
    }) => decideMcpExternalApproval(approvalId, decision),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.mcpExternalApprovals(workspaceId),
      });
    },
  });
}

export function useMcpUnknownDeliveries(enabled = true) {
  const workspaceId = useWorkspaceId();
  const params = { status: 'delivery_unknown', limit: 100, offset: 0 };
  return useQuery({
    queryKey: queryKeys.mcpExternalDeliveries(workspaceId, params),
    queryFn: () => listMcpExternalDeliveries(params),
    enabled: Boolean(workspaceId) && enabled,
    refetchInterval: enabled ? 5_000 : false,
  });
}

export function useReconcileMcpExternalDelivery() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      deliveryId,
      resolution,
    }: {
      deliveryId: string;
      resolution: 'confirmed_sent' | 'cancelled';
    }) => reconcileMcpExternalDelivery(deliveryId, resolution),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.mcpExternalDeliveries(workspaceId),
      });
    },
  });
}
