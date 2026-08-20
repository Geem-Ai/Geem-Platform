import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetRefreshStateForTests,
  apiRequest,
  buildHeaders,
  configureApiClient,
} from '@/services/api/client';
import { clearAuthSession, setAuthSession } from '@/services/auth/session';

describe('Platform Admin API client', () => {
  beforeEach(() => {
    __resetRefreshStateForTests();
    clearAuthSession();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    __resetRefreshStateForTests();
    clearAuthSession();
  });

  it('does not attach Workspace headers', () => {
    setAuthSession({ accessToken: 'tok', userId: 'u1' });
    configureApiClient({
      getAccessToken: () => 'tok',
    });
    const headers = buildHeaders();
    expect(headers.get('Authorization')).toBe('Bearer tok');
    expect(headers.has('X-Workspace-Slug')).toBe(false);
    expect(headers.has('X-Workspace-Id')).toBe(false);
  });

  it('sends fetch without workspace context', async () => {
    setAuthSession({ accessToken: 'tok', userId: 'u1' });
    configureApiClient({
      baseUrl: 'http://api.test',
      getAccessToken: () => 'tok',
    });

    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ authorized: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/api/platform/me');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = new Headers(call[1].headers);
    expect(headers.get('Authorization')).toBe('Bearer tok');
    expect(headers.get('X-Workspace-Slug')).toBeNull();
    expect(headers.get('X-Workspace-Id')).toBeNull();
  });
});
