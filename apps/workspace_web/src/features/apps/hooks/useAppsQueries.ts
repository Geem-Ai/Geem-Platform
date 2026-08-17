import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { redirectToCheckout } from '@/features/billing/lib/redirect';
import { queryKeys } from '@/services/api/query-keys';
import {
  createAppCheckout,
  createAppRenewal,
  getApp,
  installApp,
  listAppCategories,
  listAppInstallations,
  listApps,
  uninstallApp,
  type ListAppsParams,
} from '@/services/api/apps';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useAppCategories(enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.appCategories(workspaceId),
    queryFn: listAppCategories,
    enabled: Boolean(workspaceId) && enabled,
  });
}

export function useApps(params: ListAppsParams = {}, enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.apps(workspaceId, {
      category: params.category ?? '',
      billing_type: params.billing_type ?? '',
      installed:
        params.installed === undefined ? '' : String(params.installed),
      q: params.q ?? '',
      limit: params.limit,
      offset: params.offset,
    }),
    queryFn: () => listApps(params),
    enabled: Boolean(workspaceId) && enabled,
  });
}

export function useApp(slug: string | undefined, enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.app(workspaceId, slug ?? ''),
    queryFn: () => getApp(slug!),
    enabled: Boolean(workspaceId) && Boolean(slug) && enabled,
  });
}

export function useAppInstallations(enabled = true) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.appInstallations(workspaceId),
    queryFn: () => listAppInstallations({ limit: 100, offset: 0 }),
    enabled: Boolean(workspaceId) && enabled,
  });
}

export async function invalidateAppsCache(
  queryClient: ReturnType<typeof useQueryClient>,
  workspaceId: string,
  slug?: string,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.apps(workspaceId) }),
    queryClient.invalidateQueries({
      queryKey: queryKeys.appInstallations(workspaceId),
    }),
    slug
      ? queryClient.invalidateQueries({
          queryKey: queryKeys.app(workspaceId, slug),
        })
      : Promise.resolve(),
  ]);
}

export function useInstallApp() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => installApp(slug),
    onSuccess: async (_data, slug) => {
      await invalidateAppsCache(queryClient, workspaceId, slug);
    },
  });
}

export function useUninstallApp() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => uninstallApp(slug),
    onSuccess: async (_data, slug) => {
      await invalidateAppsCache(queryClient, workspaceId, slug);
    },
  });
}

export function useAppCheckout() {
  return useMutation({
    mutationFn: ({ slug, planId }: { slug: string; planId: string }) =>
      createAppCheckout(slug, planId),
    onSuccess: (checkout) => {
      redirectToCheckout(checkout.redirect_url);
    },
  });
}

export function useAppRenewal() {
  return useMutation({
    mutationFn: (slug: string) => createAppRenewal(slug),
    onSuccess: (checkout) => {
      redirectToCheckout(checkout.redirect_url);
    },
  });
}
