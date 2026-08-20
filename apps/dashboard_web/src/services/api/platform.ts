import { apiRequest } from './client';
import type {
  PlatformMeResponse,
  PlatformPageParams,
  PlatformUserDetail,
  PlatformUserListResponse,
  PlatformWorkspaceDetail,
  PlatformWorkspaceListResponse,
  PlatformWorkspaceMembersResponse,
} from './types';

function toQuery(params: PlatformPageParams = {}): string {
  const q = new URLSearchParams();
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  if (params.search?.trim()) q.set('search', params.search.trim());
  if (params.status) q.set('status', params.status);
  if (params.kind) q.set('kind', params.kind);
  if (params.platform_role) q.set('platform_role', params.platform_role);
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
    body: JSON.stringify({ reason }),
  });
}

export async function enablePlatformWorkspace(
  workspaceId: string,
  reason?: string,
): Promise<PlatformWorkspaceDetail> {
  return apiRequest<PlatformWorkspaceDetail>(`/api/platform/workspaces/${workspaceId}/enable`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason || null }),
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
    body: JSON.stringify({ reason }),
  });
}

export async function enablePlatformUser(userId: string, reason?: string): Promise<PlatformUserDetail> {
  return apiRequest<PlatformUserDetail>(`/api/platform/users/${userId}/enable`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason || null }),
  });
}

export const platformQueryKeys = {
  me: ['platform', 'me'] as const,
  workspaces: (filters: PlatformPageParams) => ['platform', 'workspaces', filters] as const,
  workspace: (id: string) => ['platform', 'workspace', id] as const,
  workspaceMembers: (id: string, filters: PlatformPageParams = {}) =>
    ['platform', 'workspace', id, 'members', filters] as const,
  users: (filters: PlatformPageParams) => ['platform', 'users', filters] as const,
  user: (id: string) => ['platform', 'user', id] as const,
};
