import { apiRequest } from './client';
import type { RoleSummary } from './types';

export type PermissionCatalogItem = {
  key: string;
  group: string;
  name_key: string;
  description_key: string;
  owner_only: boolean;
};

export type WorkspaceRoleDetail = RoleSummary & {
  workspace_id: string;
  description: string | null;
  permissions: string[];
  assigned_count: number;
  created_at: string;
  updated_at: string;
};

export type RoleListResponse = {
  items: WorkspaceRoleDetail[];
};

export type PermissionCatalogResponse = {
  items: PermissionCatalogItem[];
};

export function listWorkspacePermissions(
  workspaceId: string,
): Promise<PermissionCatalogResponse> {
  return apiRequest<PermissionCatalogResponse>(
    `/api/workspaces/${workspaceId}/permissions`,
  );
}

export function listWorkspaceRoles(workspaceId: string): Promise<RoleListResponse> {
  return apiRequest<RoleListResponse>(`/api/workspaces/${workspaceId}/roles`);
}

export function listAssignableRoles(workspaceId: string): Promise<RoleListResponse> {
  return apiRequest<RoleListResponse>(
    `/api/workspaces/${workspaceId}/roles/assignable`,
  );
}

export function createWorkspaceRole(
  workspaceId: string,
  input: { name: string; description?: string | null; permissions: string[] },
): Promise<WorkspaceRoleDetail> {
  return apiRequest<WorkspaceRoleDetail>(`/api/workspaces/${workspaceId}/roles`, {
    method: 'POST',
    json: input,
  });
}

export function updateWorkspaceRole(
  workspaceId: string,
  roleId: string,
  input: {
    name?: string;
    description?: string | null;
    permissions?: string[];
  },
): Promise<WorkspaceRoleDetail> {
  return apiRequest<WorkspaceRoleDetail>(
    `/api/workspaces/${workspaceId}/roles/${roleId}`,
    { method: 'PATCH', json: input },
  );
}

export function deleteWorkspaceRole(
  workspaceId: string,
  roleId: string,
): Promise<void> {
  return apiRequest<void>(`/api/workspaces/${workspaceId}/roles/${roleId}`, {
    method: 'DELETE',
  });
}
