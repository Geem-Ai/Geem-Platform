import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  createWorkspaceInvitation,
  listWorkspaceInvitations,
  resendWorkspaceInvitation,
  revokeWorkspaceInvitation,
  type InvitationRole,
} from '@/services/api/invitations';
import { listMembers, removeMember, updateMemberRole } from '@/services/api/workspaces';
import { queryKeys } from '@/services/api/query-keys';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useMembersList(options?: { enabled?: boolean }) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.members(workspaceId),
    queryFn: () => listMembers(workspaceId),
    enabled: Boolean(workspaceId) && (options?.enabled ?? true),
  });
}

export function usePendingInvitations(options?: { enabled?: boolean }) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.invitations(workspaceId),
    queryFn: () => listWorkspaceInvitations(workspaceId),
    enabled: Boolean(workspaceId) && (options?.enabled ?? true),
  });
}

export function useUpdateMemberRole() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      nextRole,
    }: {
      userId: string;
      nextRole: 'owner' | 'admin' | 'member';
    }) => updateMemberRole(workspaceId, userId, nextRole),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
    },
  });
}

export function useRemoveMember() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeMember(workspaceId, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
    },
  });
}

export function useCreateInvitation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; role: InvitationRole }) =>
      createWorkspaceInvitation(workspaceId, input),
    gcTime: 0,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.invitations(workspaceId),
      });
    },
  });
}

export function useResendInvitation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      resendWorkspaceInvitation(workspaceId, invitationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.invitations(workspaceId),
      });
    },
  });
}

export function useRevokeInvitation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      revokeWorkspaceInvitation(workspaceId, invitationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.invitations(workspaceId),
      });
    },
  });
}
