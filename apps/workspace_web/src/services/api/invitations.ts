import { apiRequest } from './client';

export type InvitationRole = 'admin' | 'member';

export type WorkspaceInvitationInviter = {
  id: string;
  email: string | null;
};

export type WorkspaceInvitationSummary = {
  id: string;
  workspace_id: string;
  email: string;
  role: InvitationRole | string;
  status: string;
  expires_at: string;
  created_at: string;
  invited_by: WorkspaceInvitationInviter | null;
};

export type WorkspaceInvitationList = {
  items: WorkspaceInvitationSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type InvitationAcceptResult = {
  invitation_id: string;
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  role: string;
  membership_id: string;
  already_member: boolean;
};

export function listWorkspaceInvitations(
  workspaceId: string,
  params?: { limit?: number; offset?: number },
): Promise<WorkspaceInvitationList> {
  const search = new URLSearchParams();
  if (params?.limit != null) search.set('limit', String(params.limit));
  if (params?.offset != null) search.set('offset', String(params.offset));
  const query = search.toString();
  const suffix = query ? `?${query}` : '';
  return apiRequest<WorkspaceInvitationList>(
    `/api/workspaces/${workspaceId}/invitations${suffix}`,
  );
}

export function createWorkspaceInvitation(
  workspaceId: string,
  input: { email: string; role: InvitationRole },
): Promise<WorkspaceInvitationSummary> {
  return apiRequest<WorkspaceInvitationSummary>(
    `/api/workspaces/${workspaceId}/invitations`,
    { method: 'POST', json: input },
  );
}

export function resendWorkspaceInvitation(
  workspaceId: string,
  invitationId: string,
): Promise<WorkspaceInvitationSummary> {
  return apiRequest<WorkspaceInvitationSummary>(
    `/api/workspaces/${workspaceId}/invitations/${invitationId}/resend`,
    { method: 'POST' },
  );
}

export function revokeWorkspaceInvitation(
  workspaceId: string,
  invitationId: string,
): Promise<void> {
  return apiRequest<void>(
    `/api/workspaces/${workspaceId}/invitations/${invitationId}`,
    { method: 'DELETE' },
  );
}

export function acceptWorkspaceInvitation(
  token: string,
): Promise<InvitationAcceptResult> {
  return apiRequest<InvitationAcceptResult>('/api/invitations/accept', {
    method: 'POST',
    json: { token },
    skipWorkspace: true,
  });
}
