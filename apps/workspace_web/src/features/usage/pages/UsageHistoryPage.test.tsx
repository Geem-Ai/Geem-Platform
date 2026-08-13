import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { UsageHistory, UsageHistoryItem } from '@/services/api/usage';
import { USAGE_HISTORY_PAGE_SIZE } from '@/services/api/usage';
import { UsageHistoryPage } from './UsageHistoryPage';

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: 'ws-a',
      name: 'Acme',
      slug: 'acme',
      role: 'owner',
    },
    currentMembership: {
      id: 'm1',
      workspace_id: 'ws-a',
      user_id: 'u1',
      role: 'owner',
      created_at: '2026-01-01T00:00:00Z',
    },
  }),
}));

const getUsageHistory = vi.fn();

vi.mock('@/services/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/usage')>(
    '@/services/api/usage',
  );
  return {
    ...actual,
    getUsageHistory: (params?: {
      limit?: number;
      offset?: number;
      kind?: string;
      from?: string;
      to?: string;
    }) => getUsageHistory(params),
  };
});

function item(
  id: string,
  tokens: number,
  extra: Partial<UsageHistoryItem> = {},
): UsageHistoryItem {
  return {
    id,
    kind: 'chat_tokens',
    tokens,
    credits: null,
    created_at: '2026-08-13T10:00:00Z',
    operation_type: 'chat',
    model: 'test-model',
    input_tokens: 20,
    output_tokens: 22,
    request_id: 'req-1',
    ...extra,
  };
}

function page(partial: Partial<UsageHistory> = {}): UsageHistory {
  return {
    items: [item('h1', 42)],
    total: 40,
    limit: USAGE_HISTORY_PAGE_SIZE,
    offset: 0,
    counts: { all: 40, ai: 38, credits: 2 },
    tokens: { input: 20, output: 22, total: 42 },
    ...partial,
  };
}

function renderHistory(path = '/billing/usage/history') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/billing/usage/history" element={<UsageHistoryPage />} />
          </Routes>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

describe('UsageHistoryPage', () => {
  beforeEach(async () => {
    getUsageHistory.mockReset();
    getUsageHistory.mockResolvedValue(page());
    await i18n.changeLanguage('en');
  });

  it('loads the first page of history', async () => {
    renderHistory();
    await waitFor(() => {
      expect(screen.getByTestId('usage-history-list')).toBeInTheDocument();
    });
    expect(getUsageHistory).toHaveBeenCalledWith({
      limit: USAGE_HISTORY_PAGE_SIZE,
      offset: 0,
    });
    expect(screen.getByTestId('usage-history-back')).toHaveAttribute(
      'href',
      '/billing/usage',
    );
    expect(screen.getByTestId('usage-history-next')).toHaveAttribute(
      'href',
      '/billing/usage/history?page=2',
    );
    expect(screen.getByTestId('usage-history-prev')).toBeDisabled();
    expect(screen.getByText('Chat tokens')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.queryByText('test-model')).not.toBeInTheDocument();
    expect(screen.getByText('20 in · 22 out')).toBeInTheDocument();
    expect(screen.getByTestId('usage-history-filter-all')).toHaveTextContent('40');
    expect(screen.getByTestId('usage-history-tokens-in')).toHaveTextContent('20');
    expect(screen.getByTestId('usage-history-tokens-out')).toHaveTextContent('22');
    expect(screen.getByTestId('usage-history-tokens-total')).toHaveTextContent('42');
  });

  it('requests the offset for page 2', async () => {
    getUsageHistory.mockResolvedValue(
      page({
        items: [item('h2', 9)],
        offset: USAGE_HISTORY_PAGE_SIZE,
      }),
    );
    renderHistory('/billing/usage/history?page=2');
    await waitFor(() => {
      expect(screen.getByTestId('usage-history-list')).toBeInTheDocument();
    });
    expect(getUsageHistory).toHaveBeenCalledWith({
      limit: USAGE_HISTORY_PAGE_SIZE,
      offset: USAGE_HISTORY_PAGE_SIZE,
    });
    expect(screen.getByTestId('usage-history-prev')).toHaveAttribute(
      'href',
      '/billing/usage/history',
    );
    expect(screen.getByTestId('usage-history-page-label')).toHaveTextContent(
      'Page 2 of 2',
    );
  });

  it('filters AI activity and preserves kind in pagination', async () => {
    getUsageHistory.mockResolvedValue(
      page({
        items: [item('h1', 42)],
        total: 38,
        counts: { all: 40, ai: 38, credits: 2 },
      }),
    );
    renderHistory('/billing/usage/history?kind=ai');
    await waitFor(() => {
      expect(screen.getByTestId('usage-history-list')).toBeInTheDocument();
    });
    expect(getUsageHistory).toHaveBeenCalledWith({
      limit: USAGE_HISTORY_PAGE_SIZE,
      offset: 0,
      kind: 'ai',
    });
    expect(screen.getByTestId('usage-history-filter-ai')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByTestId('usage-history-next')).toHaveAttribute(
      'href',
      '/billing/usage/history?page=2&kind=ai',
    );
    expect(screen.getByText('Chat tokens')).toBeInTheDocument();
    expect(screen.getByText('Chat')).toBeInTheDocument();
  });

  it('sends a local date range to the history API', async () => {
    renderHistory('/billing/usage/history?from=2026-08-01&to=2026-08-13');
    await waitFor(() => {
      expect(screen.getByTestId('usage-history-list')).toBeInTheDocument();
    });
    expect(getUsageHistory).toHaveBeenCalledWith(
      expect.objectContaining({
        from: expect.any(String),
        to: expect.any(String),
      }),
    );
    expect(screen.getByTestId('usage-history-from')).toHaveValue('2026-08-01');
    expect(screen.getByTestId('usage-history-to')).toHaveValue('2026-08-13');
  });

  it('retries after a load error', async () => {
    getUsageHistory.mockRejectedValueOnce(new Error('boom'));
    getUsageHistory.mockResolvedValue(page());
    renderHistory();
    await waitFor(() => {
      expect(screen.getByTestId('usage-history-error')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(screen.getByTestId('usage-history-list')).toBeInTheDocument();
    });
  });
});
