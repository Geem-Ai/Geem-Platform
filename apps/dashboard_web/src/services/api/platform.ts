import { apiRequest } from './client';
import type {
  PlatformCreditGrantBody,
  PlatformCreditGrantResponse,
  PlatformCreditHistoryResponse,
  PlatformEntitlementCatalogResponse,
  PlatformMeResponse,
  PlatformPageParams,
  PlatformPlanCreateBody,
  PlatformPlanDetail,
  PlatformPlanListResponse,
  PlatformPlanUpdateBody,
  PlatformSubscriptionAssignBody,
  PlatformSubscriptionDetail,
  PlatformSubscriptionHistoryResponse,
  PlatformUserDetail,
  PlatformUserListResponse,
  PlatformWorkspaceCredits,
  PlatformWorkspaceDetail,
  PlatformWorkspaceEntitlements,
  PlatformWorkspaceListResponse,
  PlatformWorkspaceMembersResponse,
  PlatformWorkspaceUsage,
} from './types';

function toQuery(params: PlatformPageParams = {}): string {
  const q = new URLSearchParams();
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  if (params.search?.trim()) q.set('search', params.search.trim());
  if (params.status) q.set('status', params.status);
  if (params.kind) q.set('kind', params.kind);
  if (params.platform_role) q.set('platform_role', params.platform_role);
  if (params.currency) q.set('currency', params.currency);
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function fetchPlatformMe(): Promise<PlatformMeResponse> {
  return apiRequest<PlatformMeResponse>('/api/platform/me');
}

export async function fetchPlatformWorkspaces(
  params: PlatformPageParams = {},
): Promise<PlatformWorkspaceListResponse> {
  return apiRequest<PlatformWorkspaceListResponse>(`/api/platform/workspaces${toQuery(params)}`);
}

export async function fetchPlatformWorkspace(workspaceId: string): Promise<PlatformWorkspaceDetail> {
  return apiRequest<PlatformWorkspaceDetail>(`/api/platform/workspaces/${workspaceId}`);
}

export async function fetchPlatformWorkspaceMembers(
  workspaceId: string,
  params: PlatformPageParams = {},
): Promise<PlatformWorkspaceMembersResponse> {
  return apiRequest<PlatformWorkspaceMembersResponse>(
    `/api/platform/workspaces/${workspaceId}/members${toQuery(params)}`,
  );
}

export async function disablePlatformWorkspace(
  workspaceId: string,
  reason: string,
): Promise<PlatformWorkspaceDetail> {
  return apiRequest<PlatformWorkspaceDetail>(`/api/platform/workspaces/${workspaceId}/disable`, {
    method: 'POST',
    json: { reason },
  });
}

export async function enablePlatformWorkspace(
  workspaceId: string,
  reason?: string,
): Promise<PlatformWorkspaceDetail> {
  return apiRequest<PlatformWorkspaceDetail>(`/api/platform/workspaces/${workspaceId}/enable`, {
    method: 'POST',
    json: { reason: reason || null },
  });
}

export async function fetchPlatformUsers(
  params: PlatformPageParams = {},
): Promise<PlatformUserListResponse> {
  return apiRequest<PlatformUserListResponse>(`/api/platform/users${toQuery(params)}`);
}

export async function fetchPlatformUser(userId: string): Promise<PlatformUserDetail> {
  return apiRequest<PlatformUserDetail>(`/api/platform/users/${userId}`);
}

export async function disablePlatformUser(userId: string, reason: string): Promise<PlatformUserDetail> {
  return apiRequest<PlatformUserDetail>(`/api/platform/users/${userId}/disable`, {
    method: 'POST',
    json: { reason },
  });
}

export async function enablePlatformUser(userId: string, reason?: string): Promise<PlatformUserDetail> {
  return apiRequest<PlatformUserDetail>(`/api/platform/users/${userId}/enable`, {
    method: 'POST',
    json: { reason: reason || null },
  });
}

// --- Phase 12C: Plans ---

export async function fetchPlatformPlans(
  params: PlatformPageParams = {},
): Promise<PlatformPlanListResponse> {
  return apiRequest<PlatformPlanListResponse>(`/api/platform/plans${toQuery(params)}`);
}

export async function fetchPlatformPlan(planId: string): Promise<PlatformPlanDetail> {
  return apiRequest<PlatformPlanDetail>(`/api/platform/plans/${planId}`);
}

export async function createPlatformPlan(body: PlatformPlanCreateBody): Promise<PlatformPlanDetail> {
  return apiRequest<PlatformPlanDetail>('/api/platform/plans', {
    method: 'POST',
    json: body,
  });
}

export async function updatePlatformPlan(
  planId: string,
  body: PlatformPlanUpdateBody,
): Promise<PlatformPlanDetail> {
  return apiRequest<PlatformPlanDetail>(`/api/platform/plans/${planId}`, {
    method: 'PATCH',
    json: body,
  });
}

export async function activatePlatformPlan(
  planId: string,
  reason: string,
): Promise<PlatformPlanDetail> {
  return apiRequest<PlatformPlanDetail>(`/api/platform/plans/${planId}/activate`, {
    method: 'POST',
    json: { reason },
  });
}

export async function deactivatePlatformPlan(
  planId: string,
  reason: string,
): Promise<PlatformPlanDetail> {
  return apiRequest<PlatformPlanDetail>(`/api/platform/plans/${planId}/deactivate`, {
    method: 'POST',
    json: { reason },
  });
}

export async function fetchEntitlementCatalog(): Promise<PlatformEntitlementCatalogResponse> {
  return apiRequest<PlatformEntitlementCatalogResponse>('/api/platform/entitlement-catalog');
}

// --- Phase 12C: Workspace billing ---

export async function fetchWorkspaceSubscription(
  workspaceId: string,
): Promise<PlatformSubscriptionDetail | null> {
  return apiRequest<PlatformSubscriptionDetail | null>(
    `/api/platform/workspaces/${workspaceId}/subscription`,
  );
}

export async function fetchWorkspaceSubscriptions(
  workspaceId: string,
  params: PlatformPageParams = {},
): Promise<PlatformSubscriptionHistoryResponse> {
  return apiRequest<PlatformSubscriptionHistoryResponse>(
    `/api/platform/workspaces/${workspaceId}/subscriptions${toQuery(params)}`,
  );
}

export async function assignWorkspaceSubscription(
  workspaceId: string,
  body: PlatformSubscriptionAssignBody,
): Promise<PlatformSubscriptionDetail> {
  return apiRequest<PlatformSubscriptionDetail>(
    `/api/platform/workspaces/${workspaceId}/subscription/assign`,
    {
      method: 'POST',
      json: body,
    },
  );
}

export async function fetchWorkspaceEntitlements(
  workspaceId: string,
): Promise<PlatformWorkspaceEntitlements> {
  return apiRequest<PlatformWorkspaceEntitlements>(
    `/api/platform/workspaces/${workspaceId}/entitlements`,
  );
}

export async function fetchWorkspaceUsage(workspaceId: string): Promise<PlatformWorkspaceUsage> {
  return apiRequest<PlatformWorkspaceUsage>(`/api/platform/workspaces/${workspaceId}/usage`);
}

export async function fetchWorkspaceCredits(workspaceId: string): Promise<PlatformWorkspaceCredits> {
  return apiRequest<PlatformWorkspaceCredits>(`/api/platform/workspaces/${workspaceId}/credits`);
}

export async function fetchWorkspaceCreditHistory(
  workspaceId: string,
  params: PlatformPageParams = {},
): Promise<PlatformCreditHistoryResponse> {
  return apiRequest<PlatformCreditHistoryResponse>(
    `/api/platform/workspaces/${workspaceId}/credits/history${toQuery(params)}`,
  );
}

export async function grantWorkspaceCredits(
  workspaceId: string,
  body: PlatformCreditGrantBody,
): Promise<PlatformCreditGrantResponse> {
  return apiRequest<PlatformCreditGrantResponse>(
    `/api/platform/workspaces/${workspaceId}/credits/grant`,
    {
      method: 'POST',
      json: body,
    },
  );
}

export function newCreditGrantRequestId(): string {
  return `platform-credit-grant:${crypto.randomUUID()}`;
}

export const platformQueryKeys = {
  me: ['platform', 'me'] as const,
  workspaces: (filters: PlatformPageParams) => ['platform', 'workspaces', filters] as const,
  workspace: (id: string) => ['platform', 'workspace', id] as const,
  workspaceMembers: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'workspace', id, 'members', filters] as const,
  workspaceSubscription: (id: string) => ['platform', 'workspace', id, 'subscription'] as const,
  workspaceSubscriptions: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'workspace', id, 'subscriptions', filters] as const,
  workspaceEntitlements: (id: string) => ['platform', 'workspace', id, 'entitlements'] as const,
  workspaceUsage: (id: string) => ['platform', 'workspace', id, 'usage'] as const,
  workspaceCredits: (id: string) => ['platform', 'workspace', id, 'credits'] as const,
  workspaceCreditHistory: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'workspace', id, 'credits', 'history', filters] as const,
  users: (filters: PlatformPageParams) => ['platform', 'users', filters] as const,
  user: (id: string) => ['platform', 'user', id] as const,
  plans: (filters: PlatformPageParams) => ['platform', 'plans', filters] as const,
  plan: (id: string) => ['platform', 'plan', id] as const,
  entitlementCatalog: ['platform', 'entitlement-catalog'] as const,
};
