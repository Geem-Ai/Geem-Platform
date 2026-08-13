import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  BILLING_HISTORY_PAGE_SIZE,
  createCreditPackCheckout,
  createSubscriptionCheckout,
  getPurchase,
  listBillingPlans,
  listCreditPacks,
  listPurchases,
} from '@/services/api/billing';
import { queryKeys } from '@/services/api/query-keys';
import { keepPreviousIfSameWorkspace } from '../lib/query';
import { redirectToCheckout } from '../lib/redirect';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useBillingPlans() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.billingPlans(workspaceId),
    queryFn: listBillingPlans,
    enabled: Boolean(workspaceId),
  });
}

export function useCreditPacks() {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.billingCreditPacks(workspaceId),
    queryFn: listCreditPacks,
    enabled: Boolean(workspaceId),
  });
}

export function usePurchases(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  kind?: string;
}) {
  const workspaceId = useWorkspaceId();
  const limit = params?.limit ?? BILLING_HISTORY_PAGE_SIZE;
  const offset = params?.offset ?? 0;
  const status = params?.status;
  const kind = params?.kind;
  return useQuery({
    queryKey: queryKeys.billingPurchases(workspaceId, {
      limit,
      offset,
      status,
      kind,
    }),
    queryFn: () =>
      listPurchases({
        limit,
        offset,
        ...(status ? { status } : {}),
        ...(kind ? { kind } : {}),
      }),
    enabled: Boolean(workspaceId),
    placeholderData: (previous, previousQuery) =>
      keepPreviousIfSameWorkspace(workspaceId, previous, previousQuery),
  });
}

export function usePurchase(purchaseId: string | null) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.billingPurchase(workspaceId, purchaseId ?? ''),
    queryFn: () => getPurchase(purchaseId!),
    enabled: Boolean(workspaceId && purchaseId),
  });
}

export function useInvalidateBilling() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  return async function invalidateBilling() {
    if (!workspaceId) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.subscription(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.entitlements(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.usageSummary(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.usageHistory(workspaceId) }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.billingPurchases(workspaceId),
      }),
      queryClient.invalidateQueries({ queryKey: queryKeys.billingPlans(workspaceId) }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.billingCreditPacks(workspaceId),
      }),
    ]);
  };
}

export function useSubscriptionCheckout() {
  return useMutation({
    mutationFn: (planId: string) => createSubscriptionCheckout(planId),
    onSuccess: (checkout) => {
      redirectToCheckout(checkout.redirect_url);
    },
  });
}

export function useCreditPackCheckout() {
  return useMutation({
    mutationFn: (packId: string) => createCreditPackCheckout(packId),
    onSuccess: (checkout) => {
      redirectToCheckout(checkout.redirect_url);
    },
  });
}
