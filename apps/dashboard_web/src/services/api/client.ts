import { ApiError, isKnownApiErrorCode, mapStatusToCode } from './errors';

export type ApiClientConfig = {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
  onSessionInvalid?: () => void;
  refreshAccessToken?: () => Promise<string>;
};

const SESSION_AUTH_CODES = new Set([
  'unauthorized',
  'invalid_credentials',
  'session_expired',
  'session_revoked',
]);

function peekErrorCode(body: Record<string, unknown> | undefined): string | undefined {
  const explicit =
    (typeof body?.code === 'string' && body.code) ||
    (typeof body?.error === 'string' && body.error) ||
    undefined;
  return explicit || undefined;
}

function isSessionAuthFailure(
  status: number,
  body?: Record<string, unknown>,
): boolean {
  if (status !== 401) return false;
  const code = peekErrorCode(body);
  if (!code) return true;
  if (SESSION_AUTH_CODES.has(code)) return true;
  if (isKnownApiErrorCode(code) && !SESSION_AUTH_CODES.has(code)) {
    return false;
  }
  return true;
}

export type RequestOptions = {
  method?: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  signal?: AbortSignal;
  json?: unknown;
  skipAuth?: boolean;
};

const DEFAULT_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

export async function refreshAccessTokenSingleFlight(): Promise<string> {
  if (!clientConfig.refreshAccessToken) {
    throw new ApiError('Refresh not configured', {
      status: 401,
      code: 'session_expired',
    });
  }
  if (!refreshInFlight) {
    refreshInFlight = clientConfig.refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

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
  return headers;
}

/** Headers that must never be attached by the Platform Admin client. */
export const FORBIDDEN_WORKSPACE_HEADERS = [
  'X-Workspace-Slug',
  'X-Workspace-Id',
] as const;

export function assertNoWorkspaceHeaders(headers: Headers): void {
  for (const name of FORBIDDEN_WORKSPACE_HEADERS) {
    if (headers.has(name)) {
      throw new Error(`Platform Admin client must not send ${name}`);
    }
  }
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
  assertNoWorkspaceHeaders(requestHeaders);

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

async function readErrorBody(
  res: Response,
): Promise<Record<string, unknown> | undefined> {
  try {
    return (await res.clone().json()) as Record<string, unknown>;
  } catch {
    return undefined;
  }
}

async function authorizedFetch(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const res = await rawFetch(path, options);

  if (res.status === 401 && !options.skipAuth) {
    const firstBody = await readErrorBody(res);
    if (!isSessionAuthFailure(401, firstBody)) {
      throw await parseError(res);
    }
    try {
      await refreshAccessTokenSingleFlight();
      const retry = await rawFetch(path, options);
      if (!retry.ok) {
        const err = await parseError(retry);
        const retryBody =
          err.details && typeof err.details === 'object'
            ? (err.details as Record<string, unknown>)
            : undefined;
        if (isSessionAuthFailure(retry.status, retryBody)) {
          clientConfig.onSessionInvalid?.();
        }
        throw err;
      }
      return retry;
    } catch (err) {
      if (
        err instanceof ApiError &&
        (err.code === 'session_expired' ||
          err.code === 'session_revoked' ||
          (err.status === 401 && SESSION_AUTH_CODES.has(err.code)))
      ) {
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

export async function apiRequestBlob(
  path: string,
  options: RequestOptions = {},
): Promise<Blob> {
  const res = await authorizedFetch(path, options);
  return res.blob();
}

export { buildHeaders, parseError, rawFetch };
