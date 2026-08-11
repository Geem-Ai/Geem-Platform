import type { DocumentDetail, DocumentSummary } from './types';
import { apiRequest } from './client';

/**
 * Workspace-scoped document API (Phase 2A).
 * Workspace context is sent by the shared API client (headers / host);
 * do not pass workspace_id in the body — ownership is server-side.
 */
export function listDocuments() {
  return apiRequest<DocumentSummary[]>('/api/documents');
}

export function getDocument(documentId: string, debug = false) {
  const q = debug ? '?debug=true' : '';
  return apiRequest<DocumentDetail>(`/api/documents/${documentId}${q}`);
}

export async function uploadDocument(file: File, title?: string) {
  const form = new FormData();
  form.append('file', file);
  if (title) form.append('title', title);
  return apiRequest<{ id: string; status: string; page_count: number; byte_size: number | null }>(
    '/api/documents',
    { method: 'POST', body: form },
  );
}

export function deleteDocument(documentId: string) {
  return apiRequest<{ status: string; id: string }>(`/api/documents/${documentId}`, {
    method: 'DELETE',
  });
}

export function reprocessDocument(documentId: string, mode: 'failed_pages' | 'full' = 'failed_pages') {
  return apiRequest<{ id: string; document_id: string; status: string }>(
    `/api/documents/${documentId}/reprocess`,
    {
      method: 'POST',
      body: JSON.stringify({ mode }),
      headers: { 'Content-Type': 'application/json' },
    },
  );
}
