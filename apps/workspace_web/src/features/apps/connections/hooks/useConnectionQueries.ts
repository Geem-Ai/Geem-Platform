import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { queryKeys } from '@/services/api/query-keys';
import {
  disconnectAppConnection,
  healthCheckAppConnection,
  listAppConnections,
  listConnectionSyncRuns,
  requestAppConnectionSync,
  startAppConnection,
} from '@/services/api/apps';
import { invalidateAppsCache } from '../../hooks/useAppsQueries';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useAppConnections(slug: string | undefined, enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.appConnections(workspaceId, slug ?? ''),
    queryFn: () => listAppConnections(slug!),
    enabled: Boolean(workspaceId) && Boolean(slug) && enabled,
  });
}

export function useConnectionSyncRuns(
  slug: string | undefined,
  connectionId: string | undefined,
  enabled = true,
) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.connectionSyncRuns(workspaceId, connectionId ?? ''),
    queryFn: () => listConnectionSyncRuns(slug!, connectionId!),
    enabled:
      Boolean(workspaceId) &&
      Boolean(slug) &&
      Boolean(connectionId) &&
      enabled,
  });
}

async function invalidateConnectionCache(
  queryClient: ReturnType<typeof useQueryClient>,
  workspaceId: string,
  slug: string,
  connectionId?: string,
) {
  await Promise.all([
    invalidateAppsCache(queryClient, workspaceId, slug),
    queryClient.invalidateQueries({
      queryKey: queryKeys.appConnections(workspaceId, slug),
    }),
    connectionId
      ? queryClient.invalidateQueries({
          queryKey: queryKeys.connectionSyncRuns(workspaceId, connectionId),
        })
      : Promise.resolve(),
  ]);
}

export function useStartConnection() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      slug,
      displayName,
      connectionId,
      returnPath,
      connectMode,
    }: {
      slug: string;
      displayName?: string;
      connectionId?: string;
      returnPath?: string;
      connectMode?: 'qr' | 'pairing';
    }) =>
      startAppConnection(slug, {
        display_name: displayName,
        connection_id: connectionId,
        return_path: returnPath,
        connect_mode: connectMode,
      }),
    onSuccess: async (_data, vars) => {
      await invalidateConnectionCache(queryClient, workspaceId, vars.slug);
    },
  });
}

export function useDisconnectConnection() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      slug,
      connectionId,
    }: {
      slug: string;
      connectionId: string;
    }) => disconnectAppConnection(slug, connectionId),
    onSuccess: async (_data, vars) => {
      await invalidateConnectionCache(
        queryClient,
        workspaceId,
        vars.slug,
        vars.connectionId,
      );
    },
  });
}

export function useHealthCheckConnection() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      slug,
      connectionId,
    }: {
      slug: string;
      connectionId: string;
    }) => healthCheckAppConnection(slug, connectionId),
    onSuccess: async (_data, vars) => {
      await invalidateConnectionCache(
        queryClient,
        workspaceId,
        vars.slug,
        vars.connectionId,
      );
    },
  });
}

export function useRequestConnectionSync() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      slug,
      connectionId,
    }: {
      slug: string;
      connectionId: string;
    }) => requestAppConnectionSync(slug, connectionId),
    onSuccess: async (_data, vars) => {
      await invalidateConnectionCache(
        queryClient,
        workspaceId,
        vars.slug,
        vars.connectionId,
      );
    },
  });
}
