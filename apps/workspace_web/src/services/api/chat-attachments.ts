import {
  apiRequest,
  buildHeaders,
  getApiBaseUrl,
  getApiClientConfig,
  refreshAccessTokenSingleFlight,
} from './client';
import { ApiError, mapStatusToCode } from './errors';

/**
 * Client-side UX guard. Server ``CHAT_ATTACHMENT_MAX_MB`` is authoritative.
 * Optional override: ``VITE_CHAT_ATTACHMENT_MAX_MB``.
 */
const _maxMbRaw = Number(import.meta.env.VITE_CHAT_ATTACHMENT_MAX_MB);
export const CHAT_ATTACHMENT_MAX_MB =
  Number.isFinite(_maxMbRaw) && _maxMbRaw > 0 ? _maxMbRaw : 20;
export const CHAT_ATTACHMENT_MAX_BYTES = CHAT_ATTACHMENT_MAX_MB * 1024 * 1024;

export type ChatAttachmentKind = 'images' | 'pdf' | 'text';

export const CHAT_ATTACHMENT_ACCEPT_BY_KIND: Record<ChatAttachmentKind, string> = {
  images: 'image/png,image/jpeg,image/webp,image/gif,.png,.jpg,.jpeg,.webp,.gif',
  pdf: 'application/pdf,.pdf',
  text: 'text/plain,text/markdown,.txt,.md,.markdown',
};

/** Union accept for legacy / fallback. Prefer kind-specific accept from the picker. */
export const CHAT_ATTACHMENT_ACCEPT = [
  CHAT_ATTACHMENT_ACCEPT_BY_KIND.images,
  CHAT_ATTACHMENT_ACCEPT_BY_KIND.pdf,
  CHAT_ATTACHMENT_ACCEPT_BY_KIND.text,
].join(',');

export type ChatAttachmentResponse = {
  id: string;
  original_filename: string;
  mime_type: string;
  byte_size: number;
  sha256: string;
  created_at: string;
  expires_at: string;
};

export type UploadChatAttachmentOptions = {
  signal?: AbortSignal;
  onProgress?: (percent: number) => void;
};

function parseXhrError(xhr: XMLHttpRequest): ApiError {
  let body: Record<string, unknown> | undefined;
  try {
    body = JSON.parse(xhr.responseText) as Record<string, unknown>;
  } catch {
    body = undefined;
  }
  const message =
    (typeof body?.message === 'string' && body.message) ||
    (typeof body?.detail === 'string' && body.detail) ||
    xhr.statusText ||
    'Upload failed';
  return new ApiError(message, {
    status: xhr.status,
    code: mapStatusToCode(xhr.status, body),
    details: body,
  });
}

function xhrUpload(
  path: string,
  form: FormData,
  options: UploadChatAttachmentOptions,
): Promise<ChatAttachmentResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${getApiBaseUrl()}${path}`);
    xhr.withCredentials = true;

    const headers = buildHeaders({}, {});
    headers.delete('Content-Type');
    headers.forEach((value, key) => {
      xhr.setRequestHeader(key, value);
    });

    const onAbort = () => {
      xhr.abort();
    };
    options.signal?.addEventListener('abort', onAbort);

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || !options.onProgress) return;
      const pct = Math.max(0, Math.min(99, Math.round((event.loaded / event.total) * 100)));
      options.onProgress(pct);
    };

    xhr.onload = () => {
      options.signal?.removeEventListener('abort', onAbort);
      if (xhr.status >= 200 && xhr.status < 300) {
        options.onProgress?.(100);
        try {
          resolve(JSON.parse(xhr.responseText) as ChatAttachmentResponse);
        } catch {
          reject(
            new ApiError('Invalid upload response', {
              status: xhr.status,
              code: 'unknown',
            }),
          );
        }
        return;
      }
      reject(parseXhrError(xhr));
    };

    xhr.onerror = () => {
      options.signal?.removeEventListener('abort', onAbort);
      reject(new ApiError('Network error', { status: 0, code: 'network' }));
    };

    xhr.onabort = () => {
      options.signal?.removeEventListener('abort', onAbort);
      // If the response already landed, prefer success over abort (dismiss race).
      if (xhr.status >= 200 && xhr.status < 300 && xhr.responseText) {
        try {
          options.onProgress?.(100);
          resolve(JSON.parse(xhr.responseText) as ChatAttachmentResponse);
          return;
        } catch {
          /* fall through to abort */
        }
      }
      reject(new ApiError('Upload aborted', { status: 0, code: 'aborted' }));
    };

    xhr.send(form);
  });
}

/**
 * Upload a chat composer attachment (Workspace-scoped, ephemeral).
 * Uses XHR so upload progress can drive the ChatGPT-style ring.
 */
export async function uploadChatAttachment(
  file: File,
  options: UploadChatAttachmentOptions = {},
): Promise<ChatAttachmentResponse> {
  if (file.size > CHAT_ATTACHMENT_MAX_BYTES) {
    throw new ApiError(`File exceeds the ${CHAT_ATTACHMENT_MAX_MB} MB limit`, {
      status: 413,
      code: 'upload_too_large',
      details: { max_bytes: CHAT_ATTACHMENT_MAX_BYTES, byte_size: file.size },
    });
  }

  const form = new FormData();
  form.append('file', file);

  try {
    return await xhrUpload('/api/chat/attachments', form, options);
  } catch (err) {
    if (
      err instanceof ApiError &&
      err.status === 401 &&
      getApiClientConfig().refreshAccessToken
    ) {
      await refreshAccessTokenSingleFlight();
      return xhrUpload('/api/chat/attachments', form, options);
    }
    throw err;
  }
}

export function deleteChatAttachment(attachmentId: string) {
  return apiRequest<void>(`/api/chat/attachments/${attachmentId}`, {
    method: 'DELETE',
  });
}
