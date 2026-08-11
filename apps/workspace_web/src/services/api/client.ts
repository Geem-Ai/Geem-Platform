import { ApiError, mapStatusToCode } from './errors';

export type ApiClientConfig = {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
  getWorkspaceId?: () => string | null | undefined;
  getWorkspaceSlug?: () => string | null | undefined;
  onUnauthorized?: () => void;
};

export type RequestOptions = {
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  signal?: AbortSignal;
  json?: unknown;
};

const DEFAULT_BASE_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:8000';

let clientConfig: ApiClientConfig = {
  baseUrl: DEFAULT_BASE_URL,
};

export function configureApiClient(config: ApiClientConfig): void {
  clientConfig = { ...clientConfig, ...config };
}

export function getApiBaseUrl(): string {
  return clientConfig.baseUrl || DEFAULT_BASE_URL;
}

function buildHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const token = clientConfig.getAccessToken?.();
  const workspaceId = clientConfig.getWorkspaceId?.();
  const workspaceSlug = clientConfig.getWorkspaceSlug?.();

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (workspaceId && !headers.has('X-Workspace-Id')) {
    headers.set('X-Workspace-Id', workspaceId);
  }
  if (workspaceSlug && !headers.has('X-Workspace-Slug')) {
    headers.set('X-Workspace-Slug', workspaceSlug);
  }

  return headers;
}

async function parseError(res: Response): Promise<ApiError> {
  let body: Record<string, unknown> | undefined;
  try {
    body = (await res.json()) as Record<string, unknown>;
  } catch {
    body = undefined;
  }

  const message =
    (typeof body?.message === 'string' && body.message) ||
    (typeof body?.detail === 'string' && body.detail) ||
    (typeof body?.error === 'string' && body.error) ||
    res.statusText ||
    'Request failed';

  const code = mapStatusToCode(res.status, body);
  if (code === 'unauthorized') {
    clientConfig.onUnauthorized?.();
  }

  return new ApiError(message, { status: res.status, code, details: body });
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', headers, body, signal, json } = options;
  const requestHeaders = buildHeaders(headers);

  let requestBody = body ?? null;
  if (json !== undefined) {
    requestHeaders.set('Content-Type', 'application/json');
    requestBody = JSON.stringify(json);
  }

  let res: Response;
  try {
    res = await fetch(`${getApiBaseUrl()}${path}`, {
      method,
      headers: requestHeaders,
      body: requestBody,
      signal,
    });
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      throw new ApiError('Request aborted', { status: 0, code: 'aborted' });
    }
    throw new ApiError(err instanceof Error ? err.message : 'Network error', {
      status: 0,
      code: 'network',
    });
  }

  if (!res.ok) {
    throw await parseError(res);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export { buildHeaders, parseError };
