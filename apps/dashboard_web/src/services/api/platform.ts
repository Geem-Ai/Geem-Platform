import { apiRequest, apiRequestBlob } from './client';
import type {
  PlatformCreditGrantBody,
  PlatformCreditGrantResponse,
  PlatformCreditHistoryResponse,
  PlatformEntitlementCatalogResponse,
  PlatformExpertCreateBody,
  PlatformExpertDetail,
  PlatformExpertGrantListResponse,
  PlatformExpertKnowledgeListResponse,
  PlatformExpertListResponse,
  PlatformExpertPageParams,
  PlatformExpertUpdateBody,
  PlatformExpertUploadResponse,
  PlatformExpertWorkspaceGrant,
  PlatformAppCategoryListResponse,
  PlatformAppCommercialGrantResponse,
  PlatformAppCreateBody,
  PlatformAppDetail,
  PlatformAppEntitlementCatalogResponse,
  PlatformAppLicenseGrantBody,
  PlatformAppLicenseRevokeBody,
  PlatformAppLifecycleBody,
  PlatformAppListResponse,
  PlatformAppPageParams,
  PlatformAppPlanCreateBody,
  PlatformAppPlanDetail,
  PlatformAppPlanListResponse,
  PlatformAppPlanUpdateBody,
  PlatformAppSubscriptionExtendBody,
  PlatformAppSubscriptionGrantBody,
  PlatformAppSubscriptionRevokeBody,
  PlatformAppUpdateBody,
  PlatformAppWorkspaceEntitlementListResponse,
  PlatformWorkspaceAppsResponse,
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
  PlatformPaymentGatewayCreateBody,
  PlatformPaymentGatewayDetail,
  PlatformPaymentGatewayListResponse,
  PlatformPaymentGatewayUpdateBody,
  PlatformPurchaseDetail,
  PlatformPurchaseListResponse,
  PlatformPurchasePageParams,
  PlatformPurchaseReconcileResponse,
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
  if (params.gateway) q.set('gateway', params.gateway);
  if (params.workspace_id) q.set('workspace_id', params.workspace_id);
  if (params.created_from) q.set('created_from', params.created_from);
  if (params.created_to) q.set('created_to', params.created_to);
  const s = q.toString();
  return s ? `?${s}` : '';
}

function toExpertQuery(params: PlatformExpertPageParams = {}): string {
  const q = new URLSearchParams();
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  if (params.search?.trim()) q.set('search', params.search.trim());
  if (params.status) q.set('status', params.status);
  if (params.visibility) q.set('visibility', params.visibility);
  if (params.knowledge_mode) q.set('knowledge_mode', params.knowledge_mode);
  if (params.availability_mode) q.set('availability_mode', params.availability_mode);
  if (params.published != null) q.set('published', String(params.published));
  const s = q.toString();
  return s ? `?${s}` : '';
}

function toAppQuery(params: PlatformAppPageParams = {}): string {
  const q = new URLSearchParams();
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  if (params.search?.trim()) q.set('search', params.search.trim());
  if (params.status) q.set('status', params.status);
  if (params.billing_type) q.set('billing_type', params.billing_type);
  if (params.category) q.set('category', params.category);
  if (params.connector_kind) q.set('connector_kind', params.connector_kind);
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
  experts: (filters: PlatformExpertPageParams) => ['platform', 'experts', filters] as const,
  expert: (id: string) => ['platform', 'expert', id] as const,
  expertGrants: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'expert', id, 'grants', filters] as const,
  expertKnowledge: (id: string) => ['platform', 'expert', id, 'knowledge'] as const,
  appCategories: ['platform', 'app-categories'] as const,
  apps: (filters: PlatformAppPageParams) => ['platform', 'apps', filters] as const,
  app: (id: string) => ['platform', 'app', id] as const,
  appEntitlementCatalog: (id: string) => ['platform', 'app', id, 'entitlement-catalog'] as const,
  appPlans: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'app', id, 'plans', filters] as const,
  appWorkspaces: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'app', id, 'workspaces', filters] as const,
  workspaceApps: (workspaceId: string) => ['platform', 'workspace', workspaceId, 'apps'] as const,
  paymentGateways: ['platform', 'payment-gateways'] as const,
  paymentGateway: (id: string) => ['platform', 'payment-gateway', id] as const,
  purchases: (filters: PlatformPurchasePageParams) => ['platform', 'purchases', filters] as const,
  purchase: (id: string) => ['platform', 'purchase', id] as const,
};

// --- Phase 12D: Platform Experts ---

export async function fetchPlatformExperts(
  params: PlatformExpertPageParams = {},
): Promise<PlatformExpertListResponse> {
  return apiRequest<PlatformExpertListResponse>(`/api/platform/experts${toExpertQuery(params)}`);
}

export async function fetchPlatformExpert(expertId: string): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>(`/api/platform/experts/${expertId}`);
}

export async function createPlatformExpert(
  body: PlatformExpertCreateBody,
): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>('/api/platform/experts', {
    method: 'POST',
    json: body,
  });
}

export async function updatePlatformExpert(
  expertId: string,
  body: PlatformExpertUpdateBody,
): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>(`/api/platform/experts/${expertId}`, {
    method: 'PATCH',
    json: body,
  });
}

export async function publishPlatformExpert(expertId: string): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>(`/api/platform/experts/${expertId}/publish`, {
    method: 'POST',
    json: {},
  });
}

export async function unpublishPlatformExpert(expertId: string): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>(`/api/platform/experts/${expertId}/unpublish`, {
    method: 'POST',
    json: {},
  });
}

export async function deletePlatformExpert(expertId: string): Promise<void> {
  return apiRequest<void>(`/api/platform/experts/${expertId}`, {
    method: 'DELETE',
  });
}

export async function enablePlatformExpertAllWorkspaces(
  expertId: string,
): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>(`/api/platform/experts/${expertId}/access/all`, {
    method: 'POST',
    json: {},
  });
}

export async function disablePlatformExpertAllWorkspaces(
  expertId: string,
): Promise<PlatformExpertDetail> {
  return apiRequest<PlatformExpertDetail>(`/api/platform/experts/${expertId}/access/all`, {
    method: 'DELETE',
  });
}

export async function fetchPlatformExpertGrants(
  expertId: string,
  params: PlatformPageParams = {},
): Promise<PlatformExpertGrantListResponse> {
  return apiRequest<PlatformExpertGrantListResponse>(
    `/api/platform/experts/${expertId}/workspace-grants${toQuery(params)}`,
  );
}

export async function grantPlatformExpertWorkspace(
  expertId: string,
  workspaceId: string,
): Promise<PlatformExpertWorkspaceGrant> {
  return apiRequest<PlatformExpertWorkspaceGrant>(
    `/api/platform/experts/${expertId}/workspace-grants`,
    {
      method: 'POST',
      json: { workspace_id: workspaceId },
    },
  );
}

export async function revokePlatformExpertWorkspace(
  expertId: string,
  workspaceId: string,
): Promise<void> {
  return apiRequest<void>(
    `/api/platform/experts/${expertId}/workspace-grants/${workspaceId}`,
    { method: 'DELETE' },
  );
}

export async function fetchPlatformExpertKnowledge(
  expertId: string,
): Promise<PlatformExpertKnowledgeListResponse> {
  return apiRequest<PlatformExpertKnowledgeListResponse>(
    `/api/platform/experts/${expertId}/knowledge`,
  );
}

export async function uploadPlatformExpertKnowledge(
  expertId: string,
  file: File,
  title?: string,
): Promise<PlatformExpertUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  if (title?.trim()) form.append('title', title.trim());
  return apiRequest<PlatformExpertUploadResponse>(
    `/api/platform/experts/${expertId}/knowledge`,
    { method: 'POST', body: form },
  );
}

export async function reprocessPlatformExpertKnowledge(
  expertId: string,
  documentId: string,
): Promise<{ job_id: string; status: string }> {
  return apiRequest<{ job_id: string; status: string }>(
    `/api/platform/experts/${expertId}/knowledge/${documentId}/reprocess?mode=full`,
    { method: 'POST', json: {} },
  );
}

export async function removePlatformExpertKnowledge(
  expertId: string,
  documentId: string,
): Promise<void> {
  return apiRequest<void>(`/api/platform/experts/${expertId}/knowledge/${documentId}`, {
    method: 'DELETE',
  });
}

// --- Phase 12E: Platform App Store ---

export async function fetchPlatformAppCategories(): Promise<PlatformAppCategoryListResponse> {
  return apiRequest<PlatformAppCategoryListResponse>('/api/platform/app-categories');
}

export async function fetchPlatformApps(
  params: PlatformAppPageParams = {},
): Promise<PlatformAppListResponse> {
  return apiRequest<PlatformAppListResponse>(`/api/platform/apps${toAppQuery(params)}`);
}

export async function fetchPlatformApp(appId: string): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>(`/api/platform/apps/${appId}`);
}

export async function createPlatformApp(body: PlatformAppCreateBody): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>('/api/platform/apps', {
    method: 'POST',
    json: body,
  });
}

export async function updatePlatformApp(
  appId: string,
  body: PlatformAppUpdateBody,
): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>(`/api/platform/apps/${appId}`, {
    method: 'PATCH',
    json: body,
  });
}

export async function publishPlatformApp(
  appId: string,
  body: PlatformAppLifecycleBody,
): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>(`/api/platform/apps/${appId}/publish`, {
    method: 'POST',
    json: body,
  });
}

export async function unpublishPlatformApp(
  appId: string,
  body: PlatformAppLifecycleBody,
): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>(`/api/platform/apps/${appId}/unpublish`, {
    method: 'POST',
    json: body,
  });
}

export async function setPlatformAppComingSoon(
  appId: string,
  body: PlatformAppLifecycleBody,
): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>(`/api/platform/apps/${appId}/set-coming-soon`, {
    method: 'POST',
    json: body,
  });
}

export async function disablePlatformApp(
  appId: string,
  body: PlatformAppLifecycleBody,
): Promise<PlatformAppDetail> {
  return apiRequest<PlatformAppDetail>(`/api/platform/apps/${appId}/disable`, {
    method: 'POST',
    json: body,
  });
}

export async function fetchPlatformAppEntitlementCatalog(
  appId: string,
): Promise<PlatformAppEntitlementCatalogResponse> {
  return apiRequest<PlatformAppEntitlementCatalogResponse>(
    `/api/platform/apps/${appId}/entitlement-catalog`,
  );
}

export async function fetchPlatformAppPlans(
  appId: string,
  params: PlatformPageParams = {},
): Promise<PlatformAppPlanListResponse> {
  return apiRequest<PlatformAppPlanListResponse>(
    `/api/platform/apps/${appId}/plans${toQuery(params)}`,
  );
}

export async function createPlatformAppPlan(
  appId: string,
  body: PlatformAppPlanCreateBody,
): Promise<PlatformAppPlanDetail> {
  return apiRequest<PlatformAppPlanDetail>(`/api/platform/apps/${appId}/plans`, {
    method: 'POST',
    json: body,
  });
}

export async function updatePlatformAppPlan(
  appId: string,
  planId: string,
  body: PlatformAppPlanUpdateBody,
): Promise<PlatformAppPlanDetail> {
  return apiRequest<PlatformAppPlanDetail>(`/api/platform/apps/${appId}/plans/${planId}`, {
    method: 'PATCH',
    json: body,
  });
}

export async function activatePlatformAppPlan(
  appId: string,
  planId: string,
): Promise<PlatformAppPlanDetail> {
  return apiRequest<PlatformAppPlanDetail>(
    `/api/platform/apps/${appId}/plans/${planId}/activate`,
    { method: 'POST', json: {} },
  );
}

export async function deactivatePlatformAppPlan(
  appId: string,
  planId: string,
  body: PlatformAppLifecycleBody,
): Promise<PlatformAppPlanDetail> {
  return apiRequest<PlatformAppPlanDetail>(
    `/api/platform/apps/${appId}/plans/${planId}/deactivate`,
    { method: 'POST', json: body },
  );
}

export async function fetchPlatformAppWorkspaces(
  appId: string,
  params: PlatformPageParams = {},
): Promise<PlatformAppWorkspaceEntitlementListResponse> {
  return apiRequest<PlatformAppWorkspaceEntitlementListResponse>(
    `/api/platform/apps/${appId}/workspaces${toQuery(params)}`,
  );
}

export async function fetchPlatformWorkspaceApps(
  workspaceId: string,
): Promise<PlatformWorkspaceAppsResponse> {
  return apiRequest<PlatformWorkspaceAppsResponse>(
    `/api/platform/workspaces/${workspaceId}/apps`,
  );
}

export async function grantPlatformAppLicense(
  workspaceId: string,
  appId: string,
  body: PlatformAppLicenseGrantBody,
): Promise<PlatformAppCommercialGrantResponse> {
  return apiRequest<PlatformAppCommercialGrantResponse>(
    `/api/platform/workspaces/${workspaceId}/apps/${appId}/license/grant`,
    { method: 'POST', json: body },
  );
}

export async function revokePlatformAppLicense(
  workspaceId: string,
  appId: string,
  body: PlatformAppLicenseRevokeBody,
): Promise<PlatformAppCommercialGrantResponse> {
  return apiRequest<PlatformAppCommercialGrantResponse>(
    `/api/platform/workspaces/${workspaceId}/apps/${appId}/license/revoke`,
    { method: 'POST', json: body },
  );
}

export async function grantPlatformAppSubscription(
  workspaceId: string,
  appId: string,
  body: PlatformAppSubscriptionGrantBody,
): Promise<PlatformAppCommercialGrantResponse> {
  return apiRequest<PlatformAppCommercialGrantResponse>(
    `/api/platform/workspaces/${workspaceId}/apps/${appId}/subscription/grant`,
    { method: 'POST', json: body },
  );
}

export async function extendPlatformAppSubscription(
  workspaceId: string,
  appId: string,
  body: PlatformAppSubscriptionExtendBody,
): Promise<PlatformAppCommercialGrantResponse> {
  return apiRequest<PlatformAppCommercialGrantResponse>(
    `/api/platform/workspaces/${workspaceId}/apps/${appId}/subscription/extend`,
    { method: 'POST', json: body },
  );
}

export async function revokePlatformAppSubscription(
  workspaceId: string,
  appId: string,
  body: PlatformAppSubscriptionRevokeBody,
): Promise<PlatformAppCommercialGrantResponse> {
  return apiRequest<PlatformAppCommercialGrantResponse>(
    `/api/platform/workspaces/${workspaceId}/apps/${appId}/subscription/revoke`,
    { method: 'POST', json: body },
  );
}

export function newAppGrantIdempotencyKey(): string {
  return `platform-app-grant:${crypto.randomUUID()}`;
}

// --- Phase 12F: Payment gateways ---

export async function fetchPlatformPaymentGateways(): Promise<PlatformPaymentGatewayListResponse> {
  return apiRequest<PlatformPaymentGatewayListResponse>('/api/platform/payment-gateways');
}

export async function fetchPlatformPaymentGateway(
  gatewayConfigId: string,
): Promise<PlatformPaymentGatewayDetail> {
  return apiRequest<PlatformPaymentGatewayDetail>(
    `/api/platform/payment-gateways/${gatewayConfigId}`,
  );
}

export async function createPlatformPaymentGateway(
  body: PlatformPaymentGatewayCreateBody,
): Promise<PlatformPaymentGatewayDetail> {
  return apiRequest<PlatformPaymentGatewayDetail>('/api/platform/payment-gateways', {
    method: 'POST',
    json: body,
  });
}

export async function updatePlatformPaymentGateway(
  gatewayConfigId: string,
  body: PlatformPaymentGatewayUpdateBody,
): Promise<PlatformPaymentGatewayDetail> {
  return apiRequest<PlatformPaymentGatewayDetail>(
    `/api/platform/payment-gateways/${gatewayConfigId}`,
    { method: 'PATCH', json: body },
  );
}

export async function activatePlatformPaymentGateway(
  gatewayConfigId: string,
  reason: string,
): Promise<PlatformPaymentGatewayDetail> {
  return apiRequest<PlatformPaymentGatewayDetail>(
    `/api/platform/payment-gateways/${gatewayConfigId}/activate`,
    { method: 'POST', json: { reason } },
  );
}

// --- Phase 12F: Purchases ---

function toPurchaseQuery(params: PlatformPurchasePageParams = {}): string {
  return toQuery(params);
}

export async function fetchPlatformPurchases(
  params: PlatformPurchasePageParams = {},
): Promise<PlatformPurchaseListResponse> {
  return apiRequest<PlatformPurchaseListResponse>(
    `/api/platform/purchases${toPurchaseQuery(params)}`,
  );
}

export async function fetchPlatformPurchase(purchaseId: string): Promise<PlatformPurchaseDetail> {
  return apiRequest<PlatformPurchaseDetail>(`/api/platform/purchases/${purchaseId}`);
}

export async function reconcilePlatformPurchase(
  purchaseId: string,
): Promise<PlatformPurchaseReconcileResponse> {
  return apiRequest<PlatformPurchaseReconcileResponse>(
    `/api/platform/purchases/${purchaseId}/reconcile`,
    { method: 'POST', json: {} },
  );
}

export async function downloadPlatformPurchaseInvoice(purchaseId: string): Promise<Blob> {
  return apiRequestBlob(`/api/platform/purchases/${purchaseId}/invoice`);
}
