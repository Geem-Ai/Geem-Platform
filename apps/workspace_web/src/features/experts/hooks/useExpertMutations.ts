import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { reprocessDocument } from '@/services/api/documents';
import {
  createExpert,
  deleteExpert,
  unlinkExpertDocument,
  updateExpert,
  uploadExpertDocument,
} from '@/services/api/experts';
import type { ExpertCreateInput, ExpertUpdateInput } from '@/services/api/experts';
import { queryKeys } from '@/services/api/query-keys';

function useWorkspaceId() {
  const { currentWorkspace } = useWorkspace();
  return currentWorkspace?.id ?? '';
}

export function useCreateExpert() {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (input: ExpertCreateInput) => createExpert(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.experts(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageSummary(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageHistory(workspaceId) });
    },
  });
}

export function useUpdateExpert(expertId: string) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (input: ExpertUpdateInput) => updateExpert(expertId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.expert(workspaceId, expertId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.experts(workspaceId) });
    },
  });
}

export function useDeleteExpert() {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (expertId: string) => deleteExpert(expertId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.experts(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageSummary(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageHistory(workspaceId) });
    },
  });
}

export function useUploadExpertDocument(expertId: string) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: ({
      file,
      title,
      signal,
    }: {
      file: File;
      title?: string | null;
      signal?: AbortSignal;
    }) => uploadExpertDocument(expertId, file, title ?? undefined, signal),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertKnowledge(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expert(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.experts(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageSummary(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageHistory(workspaceId) });
    },
  });
}

export function useUnlinkExpertDocument(expertId: string) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: (documentId: string) => unlinkExpertDocument(expertId, documentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertKnowledge(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expert(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.experts(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageSummary(workspaceId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.usageHistory(workspaceId) });
    },
  });
}

export function useReprocessDocument(expertId: string) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: ({
      documentId,
      mode,
    }: {
      documentId: string;
      mode?: 'failed_pages' | 'full';
    }) => reprocessDocument(documentId, mode ?? 'failed_pages'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertKnowledge(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expert(workspaceId, expertId),
      });
    },
  });
}
