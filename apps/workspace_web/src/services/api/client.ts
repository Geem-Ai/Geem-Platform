import { ApiError, mapStatusToCode } from './errors';

export type ApiClientConfig = {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
  getWorkspaceId?: () => string | null | undefined;
  /** Local DX only — backend ignores this header unless APP_ENV is local. */
  getWorkspaceSlug?: () => string | null | undefined;
  /** Called after refresh fails / session is unrecoverable. */
  onSessionInvalid?: () => void;
  /** Single-flight refresh using HttpOnly cookie. Returns new access token. */
  refreshAccessToken?: () => Promise<string>;
};

export type RequestOptions = {
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  signal?: AbortSignal;
  json?: unknown;
  /** Skip Authorization and 401 refresh (login/register/refresh). */
  skipAuth?: boolean;
  /** Do not send workspace hint headers. */
  skipWorkspace?: boolean;
};

const DEFAULT_BASE_URL =
  import.meta.env.VITE_API_URL || 'http://localhost:8000';

let clientConfig: ApiClientConfig = {
  baseUrl: DEFAULT_BASE_URL,
};

let refreshInFlight: Promise<string> | null = null;

export function configureApiClient(config: ApiClientConfig): void {
  clientConfig = { ...clientConfig, ...config };
}

export function getApiBaseUrl(): string {
  return clientConfig.baseUrl || DEFAULT_BASE_URL;
}

export function getApiClientConfig(): ApiClientConfig {
  return clientConfig;
}

/**
 * Single-flight refresh: concurrent 401s share one cookie-based refresh call.
 * Critical with rotating refresh tokens — parallel refreshes can revoke the family.
 */
export async function refreshAccessTokenSingleFlight(): Promise<string> {
  if (!clientConfig.refreshAccessToken) {
    throw new ApiError('Refresh not configured', {
      status: 401,
      code: 'session_expired',
    });
  }
  if (!refreshInFlight) {
    refreshInFlight = clientConfig
      .refreshAccessToken()
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

/** Test helper — reset in-flight refresh promise. */
export function __resetRefreshStateForTests(): void {
  refreshInFlight = null;
}

function buildHeaders(init?: HeadersInit, options?: RequestOptions): Headers {
  const headers = new Headers(init);
  if (!options?.skipAuth) {
    const token = clientConfig.getAccessToken?.();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }
  if (!options?.skipWorkspace) {
    const workspaceId = clientConfig.getWorkspaceId?.();
    const workspaceSlug = clientConfig.getWorkspaceSlug?.();
    // X-Workspace-Id: routing hint only — backend always verifies membership.
    if (workspaceId && !headers.has('X-Workspace-Id')) {
      headers.set('X-Workspace-Id', workspaceId);
    }
    // X-Workspace-Slug: local DX only (backend ignores unless APP_ENV=local).
    if (workspaceSlug && !headers.has('X-Workspace-Slug')) {
      headers.set('X-Workspace-Slug', workspaceSlug);
    }
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

  return new ApiError(message, {
    status: res.status,
    code: mapStatusToCode(res.status, body),
    details: body,
  });
}

async function rawFetch(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const { method = 'GET', headers, body, signal, json } = options;
  const requestHeaders = buildHeaders(headers, options);

  let requestBody = body ?? null;
  if (json !== undefined) {
    requestHeaders.set('Content-Type', 'application/json');
    requestBody = JSON.stringify(json);
  }

  try {
    return await fetch(`${getApiBaseUrl()}${path}`, {
      method,
      headers: requestHeaders,
      body: requestBody,
      signal,
      credentials: 'include',
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
}

async function authorizedFetch(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const res = await rawFetch(path, options);

  if (res.status === 401 && !options.skipAuth) {
    try {
      await refreshAccessTokenSingleFlight();
      const retry = await rawFetch(path, options);
      if (!retry.ok) {
        const err = await parseError(retry);
        if (retry.status === 401) {
          clientConfig.onSessionInvalid?.();
        }
        throw err;
      }
      return retry;
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.code === 'session_expired' || err.code === 'session_revoked')) {
        clientConfig.onSessionInvalid?.();
      }
      throw err;
    }
  }

  if (!res.ok) {
    throw await parseError(res);
  }

  return res;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const res = await authorizedFetch(path, options);
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export type BlobDownload = {
  blob: Blob;
  filename: string;
  contentType: string;
};

export function filenameFromContentDisposition(
  header: string | null,
  fallback = 'download',
): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      return star[1];
    }
  }
  const quoted = /filename="([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1];
  const plain = /filename=([^;]+)/i.exec(header);
  if (plain?.[1]) return plain[1].trim();
  return fallback;
}

export async function apiRequestBlob(
  path: string,
  options: RequestOptions = {},
): Promise<BlobDownload> {
  const res = await authorizedFetch(path, options);
  return {
    blob: await res.blob(),
    filename: filenameFromContentDisposition(
      res.headers.get('Content-Disposition'),
    ),
    contentType: res.headers.get('Content-Type') || 'application/octet-stream',
  };
}

export { buildHeaders, parseError, rawFetch };
