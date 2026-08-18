import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { reprocessDocument, updateDocument } from '@/services/api/documents';
import {
  createExpert,
  deleteExpert,
  deleteExpertConnectorSource,
  unlinkExpertDocument,
  updateExpert,
  uploadExpertDocument,
} from '@/services/api/experts';
import type { ExpertCreateInput, ExpertUpdateInput } from '@/services/api/experts';
import { queryKeys } from '@/services/api/query-keys';
import type { ExpertKnowledgeItem } from '@/services/api/types';

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
    mutationFn: (item: Pick<ExpertKnowledgeItem, 'document_id' | 'source_id' | 'source_type'>) => {
      if (item.source_type === 'connector' && item.source_id) {
        return deleteExpertConnectorSource(expertId, item.source_id);
      }
      if (!item.document_id) {
        throw new Error('Missing document_id');
      }
      return unlinkExpertDocument(expertId, item.document_id);
    },
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

export function useRenameExpertDocument(expertId: string) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  return useMutation({
    mutationFn: ({ documentId, title }: { documentId: string; title: string }) =>
      updateDocument(documentId, { title }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expertKnowledge(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.expert(workspaceId, expertId),
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) });
    },
  });
}
