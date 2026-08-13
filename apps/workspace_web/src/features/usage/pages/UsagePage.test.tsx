import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { Meter, Subscription, UsageHistory, UsageSummary } from '@/services/api/usage';
import { UsagePage } from './UsagePage';

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

const getUsageSummary = vi.fn();
const getUsageHistory = vi.fn();
const getSubscription = vi.fn();

vi.mock('@/services/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/usage')>(
    '@/services/api/usage',
  );
  return {
    ...actual,
    getUsageSummary: () => getUsageSummary(),
    getUsageHistory: (params?: { limit?: number; offset?: number }) =>
      getUsageHistory(params),
    getSubscription: () => getSubscription(),
  };
});

function meter(partial: Partial<Meter> = {}): Meter {
  return {
    limit: 1000,
    used: 100,
    reserved: 0,
    remaining: 900,
    period_start: '2026-08-01T00:00:00Z',
    period_end: '2026-08-02T00:00:00Z',
    ...partial,
  };
}

function summary(overrides: Partial<UsageSummary> = {}): UsageSummary {
  const daily = meter({ used: 100, remaining: 900 });
  const weekly = meter({ used: 400, remaining: 600, limit: 1000 });
  const monthly = meter({ used: 800, remaining: 200, limit: 1000 });
  return {
    ai_tokens: { daily, weekly, monthly },
    ai: { daily, weekly, monthly },
    experts: meter({ used: 2, limit: 5, remaining: 3, period_start: null, period_end: null }),
    storage_bytes: meter({
      used: 1048576,
      limit: 10485760,
      remaining: 9437184,
      period_start: null,
      period_end: null,
    }),
    storage: {
      limit_bytes: 10485760,
      used_bytes: 1048576,
      remaining_bytes: 9437184,
      reserved_bytes: 0,
      percentage: 10,
    },
    credits: { balance: 250 },
    ...overrides,
  };
}

const subscriptionA: Subscription = {
  id: 'sub-a',
  status: 'active',
  plan: { id: 'p1', code: 'bootstrap_dev', name: 'Developer', status: 'active' },
  starts_at: '2026-01-01T00:00:00Z',
  current_period_start: '2026-08-01T00:00:00Z',
  current_period_end: '2026-09-01T00:00:00Z',
  ends_at: null,
};

const history: UsageHistory = {
  items: [
    {
      id: 'h1',
      kind: 'chat_tokens',
      tokens: 42,
      credits: null,
      created_at: '2026-08-13T10:00:00Z',
    },
    {
      id: 'h2',
      kind: 'credit_grant',
      tokens: null,
      credits: 100,
      created_at: '2026-08-12T10:00:00Z',
    },
  ],
  total: 2,
  limit: 10,
  offset: 0,
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
            <UsagePage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('UsagePage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    getUsageSummary.mockReset();
    getUsageHistory.mockReset();
    getSubscription.mockReset();
    getUsageSummary.mockResolvedValue(summary());
    getUsageHistory.mockResolvedValue(history);
    getSubscription.mockResolvedValue(subscriptionA);
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('renders usage summary, token meters, storage, experts, and credits', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-plan-name')).toHaveTextContent('Developer');
    });
    expect(screen.getByTestId('usage-ai-daily')).toBeInTheDocument();
    expect(screen.getByTestId('usage-ai-weekly')).toBeInTheDocument();
    expect(screen.getByTestId('usage-ai-monthly')).toBeInTheDocument();
    expect(screen.getByTestId('usage-experts-used')).toHaveTextContent('2');
    expect(screen.getByTestId('usage-experts-limit')).toHaveTextContent('5');
    expect(screen.getByTestId('usage-storage')).toBeInTheDocument();
    expect(screen.getByTestId('usage-credits-balance')).toHaveTextContent('250');
    expect(screen.getByTestId('usage-history-list')).toBeInTheDocument();
    expect(screen.getByText('Chat tokens')).toBeInTheDocument();
    expect(screen.getByTestId('usage-history-view-all')).toHaveAttribute(
      'href',
      '/billing/usage/history',
    );
    expect(getUsageHistory).toHaveBeenCalledWith({ limit: 10, offset: 0 });
  });

  it('shows approaching warning on the monthly meter at 80%', async () => {
    getUsageSummary.mockResolvedValue(
      summary({
        ai: {
          daily: meter(),
          weekly: meter(),
          monthly: meter({ used: 800, limit: 1000, remaining: 200 }),
        },
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-ai-monthly-level')).toHaveAttribute(
        'data-level',
        'approaching',
      );
    });
  });

  it('shows exhausted state at 100%', async () => {
    getUsageSummary.mockResolvedValue(
      summary({
        experts: meter({
          used: 3,
          limit: 3,
          remaining: 0,
          period_start: null,
          period_end: null,
        }),
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-experts-level')).toHaveAttribute(
        'data-level',
        'exhausted',
      );
    });
    expect(screen.getByTestId('usage-experts-level')).toHaveTextContent('Exhausted');
  });

  it('presents unlimited entitlements when the backend sends a negative limit', async () => {
    getUsageSummary.mockResolvedValue(
      summary({
        experts: meter({
          used: 2,
          limit: -1,
          remaining: 999,
          period_start: null,
          period_end: null,
        }),
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-experts-limit')).toHaveTextContent('Unlimited');
    });
  });

  it('presents missing allowance when limit is zero', async () => {
    getUsageSummary.mockResolvedValue(
      summary({
        experts: meter({
          used: 0,
          limit: 0,
          remaining: 0,
          period_start: null,
          period_end: null,
        }),
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No allowance on this plan')).toBeInTheDocument();
    });
  });

  it('shows a loading state before data arrives', () => {
    getUsageSummary.mockReturnValue(new Promise(() => undefined));
    getSubscription.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByTestId('usage-loading')).toBeInTheDocument();
  });

  it('shows an API error state with retry', async () => {
    getUsageSummary.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-error')).toBeInTheDocument();
    });
    getUsageSummary.mockResolvedValue(summary());
    fireEvent.click(
      within(screen.getByTestId('usage-error')).getByRole('button', { name: 'Retry' }),
    );
    await waitFor(() => {
      expect(screen.getByTestId('usage-plan-name')).toHaveTextContent('Developer');
    });
  });

  it('isolates cached usage across workspace switches', async () => {
    const { client, rerender } = renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-plan-name')).toHaveTextContent('Developer');
    });
    expect(queryKeys.usageSummary('ws-a')).not.toEqual(queryKeys.usageSummary('ws-b'));
    expect(client.getQueryData(queryKeys.usageSummary('ws-a'))).toBeTruthy();

    workspaceState.id = 'ws-b';
    getSubscription.mockResolvedValue({
      ...subscriptionA,
      id: 'sub-b',
      plan: { ...subscriptionA.plan, name: 'Workspace B Plan' },
    });
    getUsageSummary.mockResolvedValue(
      summary({ credits: { balance: 1 } }),
    );

    rerender(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <UsagePage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('usage-plan-name')).toHaveTextContent('Workspace B Plan');
    });
    expect(screen.queryByText('Developer')).not.toBeInTheDocument();
    expect(screen.getByTestId('usage-credits-balance')).toHaveTextContent('1');
  });

  it('renders Arabic copy and RTL document direction', async () => {
    await i18n.changeLanguage('ar');
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('usage-credits')).toBeInTheDocument();
    });
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByRole('heading', { name: 'الاستخدام' })).toBeInTheDocument();
    expect(screen.getByTestId('usage-credits')).toHaveTextContent('الرصيد الإضافي');
  });
});
