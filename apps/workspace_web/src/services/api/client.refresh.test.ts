import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetRefreshStateForTests,
  apiRequest,
  configureApiClient,
  refreshAccessTokenSingleFlight,
} from '@/services/api/client';
import { setAuthSession, clearAuthSession } from '@/services/auth/session';

describe('api client refresh single-flight', () => {
  beforeEach(() => {
    __resetRefreshStateForTests();
    clearAuthSession();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    __resetRefreshStateForTests();
    clearAuthSession();
  });

  it('dedupes concurrent refresh calls into one', async () => {
    let refreshCalls = 0;
    configureApiClient({
      baseUrl: 'http://api.test',
      refreshAccessToken: async () => {
        refreshCalls += 1;
        await new Promise((r) => setTimeout(r, 30));
        setAuthSession({ accessToken: 'new-token', userId: 'u1' });
        return 'new-token';
      },
    });

    const [a, b, c] = await Promise.all([
      refreshAccessTokenSingleFlight(),
      refreshAccessTokenSingleFlight(),
      refreshAccessTokenSingleFlight(),
    ]);

    expect(refreshCalls).toBe(1);
    expect(a).toBe('new-token');
    expect(b).toBe('new-token');
    expect(c).toBe('new-token');
  });

  it('retries original request once after 401 refresh', async () => {
    let refreshCalls = 0;
    let call = 0;
    setAuthSession({ accessToken: 'expired', userId: 'u1' });

    configureApiClient({
      baseUrl: 'http://api.test',
      getAccessToken: () => (call === 0 ? 'expired' : 'fresh'),
      refreshAccessToken: async () => {
        refreshCalls += 1;
        setAuthSession({ accessToken: 'fresh', userId: 'u1' });
        return 'fresh';
      },
    });

    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        const auth = new Headers(init?.headers).get('Authorization');
        call += 1;
        if (auth === 'Bearer expired') {
          return new Response(JSON.stringify({ code: 'session_expired', message: 'expired' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }),
    );

    const result = await apiRequest<{ ok: boolean }>('/api/workspaces');
    expect(result.ok).toBe(true);
    expect(refreshCalls).toBe(1);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('does not logout on connector 401 codes', async () => {
    const onSessionInvalid = vi.fn();
    const refreshAccessToken = vi.fn(async () => 'fresh');
    setAuthSession({ accessToken: 'tok', userId: 'u1' });

    configureApiClient({
      baseUrl: 'http://api.test',
      getAccessToken: () => 'tok',
      onSessionInvalid,
      refreshAccessToken,
    });

    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: 'microsoft_onedrive_authorization_failed',
            message: 'Microsoft authorization failed.',
          }),
          {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          },
        ),
      ),
    );

    await expect(
      apiRequest('/api/apps/microsoft-onedrive/connections/x/picker-session', {
        method: 'POST',
      }),
    ).rejects.toMatchObject({
      code: 'microsoft_onedrive_authorization_failed',
      status: 401,
    });
    expect(refreshAccessToken).not.toHaveBeenCalled();
    expect(onSessionInvalid).not.toHaveBeenCalled();
  });

  it('calls onSessionInvalid when refresh fails', async () => {
    const onSessionInvalid = vi.fn();
    setAuthSession({ accessToken: 'expired', userId: 'u1' });

    configureApiClient({
      baseUrl: 'http://api.test',
      getAccessToken: () => 'expired',
      onSessionInvalid,
      refreshAccessToken: async () => {
        throw Object.assign(new Error('revoked'), {
          name: 'ApiError',
          status: 401,
          code: 'session_revoked',
        });
      },
    });

    // Make refreshAccessToken throw ApiError properly
    const { ApiError } = await import('@/services/api/errors');
    configureApiClient({
      baseUrl: 'http://api.test',
      getAccessToken: () => 'expired',
      onSessionInvalid,
      refreshAccessToken: async () => {
        throw new ApiError('revoked', { status: 401, code: 'session_revoked' });
      },
    });

    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ code: 'session_expired' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );

    await expect(apiRequest('/api/workspaces')).rejects.toBeTruthy();
    expect(onSessionInvalid).toHaveBeenCalled();
  });
});
