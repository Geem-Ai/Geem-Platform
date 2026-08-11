import { apiRequest } from './client';
import type { Member, Workspace } from './types';

export async function listWorkspaces(): Promise<Workspace[]> {
  return apiRequest<Workspace[]>('/api/workspaces');
}

export async function createWorkspace(input: {
  name: string;
  slug: string;
}): Promise<Workspace> {
  return apiRequest<Workspace>('/api/workspaces', {
    method: 'POST',
    json: input,
  });
}

export async function getWorkspace(workspaceId: string): Promise<Workspace> {
  return apiRequest<Workspace>(`/api/workspaces/${workspaceId}`);
}

export async function updateWorkspace(
  workspaceId: string,
  input: { name?: string; settings?: Record<string, unknown> },
): Promise<Workspace> {
  return apiRequest<Workspace>(`/api/workspaces/${workspaceId}`, {
    method: 'PATCH',
    json: input,
  });
}

export async function listMembers(workspaceId: string): Promise<Member[]> {
  return apiRequest<Member[]>(`/api/workspaces/${workspaceId}/members`);
}

export async function updateMemberRole(
  workspaceId: string,
  userId: string,
  role: 'owner' | 'admin' | 'member',
): Promise<Member> {
  return apiRequest<Member>(`/api/workspaces/${workspaceId}/members/${userId}`, {
    method: 'PATCH',
    json: { role },
  });
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
  await apiRequest<void>(`/api/workspaces/${workspaceId}/members/${userId}`, {
    method: 'DELETE',
  });
}
