import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  clearConversationHistory,
  createConversation,
  deleteConversation,
  updateConversation,
  type ConversationCreateInput,
  type ConversationUpdateInput,
} from '@/services/api/conversations';
import { queryKeys, workspaceQueryKey } from '@/services/api/query-keys';
import type { Conversation } from '@/services/api/types';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useCreateConversation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ConversationCreateInput) => createConversation(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.conversations(workspaceId),
        exact: true,
      });
    },
  });
}

export function useUpdateConversation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      conversationId,
      input,
    }: {
      conversationId: string;
      input: ConversationUpdateInput;
    }) => updateConversation(conversationId, input),
    onSuccess: async (updated: Conversation) => {
      queryClient.setQueryData(
        queryKeys.conversation(workspaceId, updated.id),
        updated,
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.conversations(workspaceId),
        exact: true,
      });
    },
  });
}

export function useDeleteConversation() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (conversationId: string) => deleteConversation(conversationId),
    onSuccess: async (_data, conversationId) => {
      queryClient.removeQueries({
        queryKey: queryKeys.conversation(workspaceId, conversationId),
        exact: true,
      });
      queryClient.removeQueries({
        queryKey: queryKeys.conversationMessages(workspaceId, conversationId),
        exact: true,
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.conversations(workspaceId),
        exact: true,
      });
    },
  });
}

export function useClearConversationHistory() {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => clearConversationHistory(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: workspaceQueryKey(workspaceId, 'conversations'),
      });
    },
  });
}
