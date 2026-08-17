import type {
  Expert,
  ExpertDocumentLink,
  ExpertKnowledgeItem,
  ExpertRagConfig,
  ExpertSource,
  ExpertUploadResponse,
} from './types';
import { apiRequest, buildHeaders, getApiBaseUrl } from './client';
import { ApiError, mapStatusToCode } from './errors';

/**
 * Workspace Expert API client (Phase 3C).
 * Workspace context comes from the shared API client; never send ownership workspace_id.
 */

export type ExpertCreateInput = {
  name: string;
  description?: string | null;
  system_instructions?: string | null;
  rag_config?: ExpertRagConfig | null;
  visibility?: string | null;
  status?: string | null;
  icon_url?: string | null;
};

export type ExpertUpdateInput = Partial<ExpertCreateInput>;

export type GenerateExpertInstructionsInput = {
  brief: string;
  persona?: string | null;
  audience?: string | null;
  tone?: string | null;
  constraints?: string | null;
  name?: string | null;
  description?: string | null;
};

export type GenerateExpertInstructionsResult = {
  system_instructions: string;
};

export function listExperts() {
  return apiRequest<Expert[]>('/api/experts');
}

export function getExpert(expertId: string) {
  return apiRequest<Expert>(`/api/experts/${expertId}`);
}

export function createExpert(input: ExpertCreateInput) {
  return apiRequest<Expert>('/api/experts', { method: 'POST', json: input });
}

export function updateExpert(expertId: string, input: ExpertUpdateInput) {
  return apiRequest<Expert>(`/api/experts/${expertId}`, {
    method: 'PATCH',
    json: input,
  });
}

/** Draft system instructions via OpenRouter (bills workspace AI chat tokens). */
export function generateExpertInstructions(input: GenerateExpertInstructionsInput) {
  return apiRequest<GenerateExpertInstructionsResult>(
    '/api/experts/generate-instructions',
    {
      method: 'POST',
      json: {
        brief: input.brief,
        persona: input.persona ?? null,
        audience: input.audience ?? null,
        tone: input.tone ?? null,
        constraints: input.constraints ?? null,
        name: input.name ?? null,
        description: input.description ?? null,
      },
    },
  );
}

export function deleteExpert(expertId: string) {
  return apiRequest<void>(`/api/experts/${expertId}`, { method: 'DELETE' });
}

/** Returns enriched knowledge items (Phase 3C). */
export function listExpertDocuments(expertId: string) {
  return apiRequest<ExpertKnowledgeItem[]>(`/api/experts/${expertId}/documents`);
}

export function linkExpertDocument(
  expertId: string,
  documentId: string,
  sourceId?: string | null,
) {
  return apiRequest<ExpertDocumentLink>(`/api/experts/${expertId}/documents`, {
    method: 'POST',
    json: { document_id: documentId, source_id: sourceId ?? null },
  });
}

/** Remove a document from an expert (membership only — document not deleted from workspace). */
export function unlinkExpertDocument(expertId: string, documentId: string) {
  return apiRequest<void>(`/api/experts/${expertId}/documents/${documentId}`, {
    method: 'DELETE',
  });
}

/** Soft-delete a connector-backed ExpertSource (Google Drive / future OneDrive). */
export function deleteExpertConnectorSource(expertId: string, sourceId: string) {
  return apiRequest<void>(`/api/experts/${expertId}/sources/${sourceId}`, {
    method: 'DELETE',
  });
}

/** Alias for unlinkExpertDocument matching Phase 3C naming convention. */
export const deleteExpertSource = unlinkExpertDocument;

/**
 * Upload a file directly to an expert via multipart/form-data.
 * Returns ExpertUploadResponse including `reused` flag.
 */
export async function uploadExpertDocument(
  expertId: string,
  file: File,
  title?: string | null,
  signal?: AbortSignal,
): Promise<ExpertUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (title?.trim()) {
    formData.append('title', title.trim());
  }

  const headers = buildHeaders({}, {});
  // Browser must set Content-Type with multipart boundary — remove any preset value.
  headers.delete('Content-Type');

  let res: Response;
  try {
    res = await fetch(`${getApiBaseUrl()}/api/experts/${expertId}/upload`, {
      method: 'POST',
      headers,
      body: formData,
      signal,
      credentials: 'include',
    });
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      throw new ApiError('Upload aborted', { status: 0, code: 'aborted' });
    }
    throw new ApiError(err instanceof Error ? err.message : 'Network error', {
      status: 0,
      code: 'network',
    });
  }

  if (!res.ok) {
    let body: Record<string, unknown> | undefined;
    try {
      body = (await res.json()) as Record<string, unknown>;
    } catch { /* ignore */ }
    const message =
      (typeof body?.message === 'string' && body.message) ||
      (typeof body?.detail === 'string' && body.detail) ||
      res.statusText ||
      'Upload failed';
    throw new ApiError(message, { status: res.status, code: mapStatusToCode(res.status, body) });
  }

  return (await res.json()) as ExpertUploadResponse;
}

export function createExpertSource(expertId: string, name?: string | null) {
  return apiRequest<ExpertSource>(`/api/experts/${expertId}/sources`, {
    method: 'POST',
    json: { name: name ?? null, type: 'upload' },
  });
}

export type ConnectorSourceItemInput = {
  external_id?: string | null;
  resource_key?: string | null;
  provider_locator?: Record<string, string> | null;
};

export type ConnectorSourcesCreateResponse = {
  sources: ExpertSource[];
  sync_run_id: string | null;
  status: string;
};

/** Attach provider files (Google Drive / Microsoft OneDrive) as Expert knowledge sources. */
export function createExpertConnectorSources(
  expertId: string,
  body: {
    connection_id: string;
    items: ConnectorSourceItemInput[];
  },
) {
  return apiRequest<ConnectorSourcesCreateResponse>(
    `/api/experts/${expertId}/connector-sources`,
    {
      method: 'POST',
      json: {
        connection_id: body.connection_id,
        items: body.items.map((item) => ({
          external_id: item.external_id ?? null,
          resource_key: item.resource_key ?? null,
          provider_locator: item.provider_locator ?? null,
        })),
      },
    },
  );
}
