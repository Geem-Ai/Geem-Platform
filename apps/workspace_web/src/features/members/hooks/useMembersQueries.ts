import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  createWorkspaceInvitation,
  listWorkspaceInvitations,
  resendWorkspaceInvitation,
  revokeWorkspaceInvitation,
} from '@/services/api/invitations';
import {
  createWorkspaceRole,
  deleteWorkspaceRole,
  listAssignableRoles,
  listWorkspacePermissions,
  listWorkspaceRoles,
  updateWorkspaceRole,
} from '@/services/api/roles';
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

export function useWorkspaceRoles(options?: { enabled?: boolean }) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.roles(workspaceId),
    queryFn: () => listWorkspaceRoles(workspaceId),
    enabled: Boolean(workspaceId) && (options?.enabled ?? true),
  });
}

export function useAssignableRoles(options?: { enabled?: boolean }) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.assignableRoles(workspaceId),
    queryFn: () => listAssignableRoles(workspaceId),
    enabled: Boolean(workspaceId) && (options?.enabled ?? true),
  });
}

export function usePermissionCatalog(options?: { enabled?: boolean }) {
  const workspaceId = useWorkspaceId();
  return useQuery({
    queryKey: queryKeys.permissionCatalog(workspaceId),
    queryFn: () => listWorkspacePermissions(workspaceId),
    enabled: Boolean(workspaceId) && (options?.enabled ?? true),
  });
}

export function useUpdateMemberRole() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, roleId }: { userId: string; roleId: string }) =>
      updateMemberRole(workspaceId, userId, roleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.members(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles(workspaceId) });
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
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles(workspaceId) });
    },
  });
}

export function useCreateInvitation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; role_id: string }) =>
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

export function useCreateRole() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      name: string;
      description?: string | null;
      permissions: string[];
    }) => createWorkspaceRole(workspaceId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles(workspaceId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assignableRoles(workspaceId),
      });
    },
  });
}

export function useUpdateRole() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      roleId,
      ...input
    }: {
      roleId: string;
      name?: string;
      description?: string | null;
      permissions?: string[];
    }) => updateWorkspaceRole(workspaceId, roleId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles(workspaceId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assignableRoles(workspaceId),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
  });
}

export function useDeleteRole() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (roleId: string) => deleteWorkspaceRole(workspaceId, roleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.roles(workspaceId) });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assignableRoles(workspaceId),
      });
    },
  });
}
