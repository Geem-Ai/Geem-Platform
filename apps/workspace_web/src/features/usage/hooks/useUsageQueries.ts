import { useQuery } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { queryKeys } from '@/services/api/query-keys';
import {
  getEntitlements,
  getSubscription,
  getUsageHistory,
  getUsageSummary,
  USAGE_HISTORY_PREVIEW_LIMIT,
} from '@/services/api/usage';
import {
  exclusiveEndOfLocalDayIso,
  startOfLocalDayIso,
} from '../lib/history';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useUsageSummary() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.usageSummary(workspaceId),
    queryFn: getUsageSummary,
    enabled: Boolean(workspaceId),
  });
}

export function useUsageHistory(params?: {
  limit?: number;
  offset?: number;
  kind?: string;
  from?: string | null;
  to?: string | null;
}) {
  const workspaceId = useWorkspaceId();
  const limit = params?.limit ?? USAGE_HISTORY_PREVIEW_LIMIT;
  const offset = params?.offset ?? 0;
  const kind = params?.kind ?? 'all';
  const from = params?.from ?? undefined;
  const to = params?.to ?? undefined;
  return useQuery({
    queryKey: queryKeys.usageHistory(workspaceId, {
      limit,
      offset,
      kind,
      from,
      to,
    }),
    queryFn: () => {
      const fromIso = from ? startOfLocalDayIso(from) : undefined;
      const toIso = to ? exclusiveEndOfLocalDayIso(to) : undefined;
      return getUsageHistory({
        limit,
        offset,
        ...(kind !== 'all' ? { kind } : {}),
        ...(fromIso ? { from: fromIso } : {}),
        ...(toIso ? { to: toIso } : {}),
      });
    },
    enabled: Boolean(workspaceId),
    placeholderData: (previous) => previous,
  });
}

export function useSubscription() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.subscription(workspaceId),
    queryFn: getSubscription,
    enabled: Boolean(workspaceId),
  });
}

export function useEntitlements() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.entitlements(workspaceId),
    queryFn: getEntitlements,
    enabled: Boolean(workspaceId),
  });
}
