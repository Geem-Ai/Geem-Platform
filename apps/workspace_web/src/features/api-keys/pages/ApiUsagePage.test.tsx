import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { ApiUsageHistory, ApiUsageSummary } from '@/services/api/api-keys';
import { ApiUsagePage } from './ApiUsagePage';

const workspaceState = { id: 'ws-a' };

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: workspaceState.id,
      name: 'Acme',
      slug: 'acme',
      role: 'owner',
    },
    currentMembership: {
      id: 'm1',
      workspace_id: workspaceState.id,
      user_id: 'u1',
      role: 'owner',
      created_at: '2026-01-01T00:00:00Z',
    },
  }),
}));

const getApiUsageSummary = vi.fn();
const getApiUsageHistory = vi.fn();

vi.mock('@/services/api/api-keys', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/api-keys')>(
    '@/services/api/api-keys',
  );
  return {
    ...actual,
    getApiUsageSummary: (period?: string) => getApiUsageSummary(period),
    getApiUsageHistory: (params?: unknown) => getApiUsageHistory(params),
  };
});

function summary(overrides: Partial<ApiUsageSummary> = {}): ApiUsageSummary {
  return {
    rate_limit: { requests_per_minute: 60 },
    ai_tokens: { billed: 42120 },
    workspace_ai_monthly: {
      limit: 5_000_000,
      used: 2_100_000,
      reserved: 0,
      remaining: 2_900_000,
      period_start: '2026-08-01T00:00:00Z',
      period_end: '2026-09-01T00:00:00Z',
    },
    period: {
      key: '30d',
      from_at: '2026-07-14T00:00:00Z',
      to_at: '2026-08-13T00:00:00Z',
    },
    keys: [
      {
        api_key_id: 'key-1',
        name: 'Production',
        prefix: 'geem_sk_abcd1234',
        last_four: 'wxyz',
        billed_tokens: 42120,
        last_used_at: '2026-08-13T10:00:00Z',
        expires_at: null,
        revoked_at: null,
      },
    ],
    ...overrides,
  };
}

const history: ApiUsageHistory = {
  items: [
    {
      id: 'evt-1',
      created_at: '2026-08-13T10:00:00Z',
      api_key_id: 'key-1',
      api_key_name: 'Production',
      prefix: 'geem_sk_abcd1234',
      last_four: 'wxyz',
      expert_id: 'exp-1',
      family: 'chat',
      model: 'test-model',
      billed_tokens: 42,
      operation_type: 'chat',
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
  period: summary().period,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <ApiUsagePage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('ApiUsagePage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    getApiUsageSummary.mockReset();
    getApiUsageHistory.mockReset();
    getApiUsageSummary.mockResolvedValue(summary());
    getApiUsageHistory.mockResolvedValue(history);
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('shows rate limit, shared AI pool, per-key usage, and billing link', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-usage-rate-limit')).toHaveTextContent(
        '60 requests / minute',
      );
    });
    expect(screen.getByTestId('api-usage-ai-tokens')).toHaveTextContent('42,120');
    expect(screen.getByTestId('api-usage-full-usage')).toHaveAttribute(
      'href',
      '/billing/usage',
    );
    expect(screen.getByTestId('api-usage-key-key-1')).toHaveTextContent('Production');
    expect(screen.getByTestId('api-usage-key-key-1').textContent).toContain(
      'geem_sk_abcd1234••••wxyz',
    );
    expect(screen.getByTestId('api-usage-monthly-pool')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /about api request limit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /about api ai tokens/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /manage keys/i })).toHaveAttribute(
      'href',
      '/api/keys',
    );
    expect(screen.queryByText(/geem_sk_[a-zA-Z0-9_-]{20,}/)).not.toBeInTheDocument();
  });

  it('shows empty usage history', async () => {
    getApiUsageHistory.mockResolvedValue({ ...history, items: [], total: 0 });
    getApiUsageSummary.mockResolvedValue(summary({ keys: [], ai_tokens: { billed: 0 } }));
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-usage-history-empty')).toBeInTheDocument();
    });
    expect(screen.getByTestId('api-usage-no-keys')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /create api key/i })).toHaveAttribute(
      'href',
      '/api/keys',
    );
  });

  it('shows an error with retry', async () => {
    getApiUsageSummary.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-usage-error')).toBeInTheDocument();
    });
  });

  it('scopes usage queries by workspace id', async () => {
    renderPage();
    await waitFor(() => {
      expect(getApiUsageSummary).toHaveBeenCalled();
    });
    expect(queryKeys.apiUsageSummary('ws-a', '30d')[1]).toBe('ws-a');
    expect(queryKeys.apiUsageSummary('ws-b', '30d')[1]).toBe('ws-b');
  });

  it('does not show workspace A usage after switching to B', async () => {
    getApiUsageSummary.mockImplementation(async () => {
      if (workspaceState.id === 'ws-a') {
        return summary({ keys: [{ ...summary().keys[0], name: 'Alpha Prod' }] });
      }
      return summary({
        ai_tokens: { billed: 9 },
        keys: [
          {
            api_key_id: 'key-b',
            name: 'Beta Prod',
            prefix: 'geem_sk_bbbbbbbb',
            last_four: 'zzzz',
            billed_tokens: 9,
            last_used_at: null,
            expires_at: null,
            revoked_at: null,
          },
        ],
      });
    });
    const { rerender, client } = renderPage();
    await waitFor(() => expect(screen.getByText('Alpha Prod')).toBeInTheDocument());

    workspaceState.id = 'ws-b';
    rerender(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <ApiUsagePage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('Beta Prod')).toBeInTheDocument());
    expect(screen.queryByText('Alpha Prod')).not.toBeInTheDocument();
  });
});
