import { act, fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { McpServerDetailPage } from './McpServerDetailPage';

const mocks = vi.hoisted(() => ({
  useMcpTools: vi.fn(),
  toolList: {
    items: [] as unknown[],
    total: 47,
    limit: 25,
    offset: 0,
  },
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/authz/usePermissions', () => ({
  usePermissions: () => ({ can: () => true }),
}));

vi.mock('@/features/experts/hooks/useExperts', () => ({
  useExperts: () => ({ data: [], isLoading: false }),
}));

vi.mock('../hooks/useMcpQueries', () => ({
  useMcpServer: () => ({
    data: {
      id: 'server-id',
      display_name: 'GitHub',
      endpoint_host: 'api.githubcopilot.com',
      status: 'active',
      health: 'healthy',
      protocol_version: '2026-07-28',
      session_mode: 'modern',
    },
    error: null,
  }),
  useMcpTools: (...args: unknown[]) => {
    mocks.useMcpTools(...args);
    return {
      data: mocks.toolList,
      isLoading: false,
      isFetching: false,
      error: null,
    };
  },
  useExpertMcpGrants: () => ({ data: [] }),
  useDiscoverMcpTools: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateMcpToolClassification: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useCreateExpertMcpGrant: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRevokeExpertMcpGrant: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/apps/mcp/server-id']}>
        <Routes>
          <Route path="/apps/mcp/:connectionId" element={<McpServerDetailPage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('McpServerDetailPage tool search', () => {
  beforeEach(async () => {
    vi.useFakeTimers();
    mocks.useMcpTools.mockReset();
    mocks.toolList.items = [];
    mocks.toolList.total = 47;
    await i18n.changeLanguage('en');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('debounces full-inventory search and resets pagination', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(mocks.useMcpTools).toHaveBeenCalledWith('server-id', {
      limit: 25,
      offset: 25,
      q: '',
    });

    fireEvent.change(screen.getByTestId('mcp-tools-search'), {
      target: { value: 'pull request' },
    });
    act(() => vi.advanceTimersByTime(299));
    expect(mocks.useMcpTools).not.toHaveBeenCalledWith('server-id', {
      limit: 25,
      offset: 0,
      q: 'pull request',
    });

    act(() => vi.advanceTimersByTime(1));
    expect(mocks.useMcpTools).toHaveBeenCalledWith('server-id', {
      limit: 25,
      offset: 0,
      q: 'pull request',
    });
  });

  it('shows a filtered empty state and clears the query immediately', () => {
    mocks.toolList.total = 0;
    renderPage();

    fireEvent.change(screen.getByTestId('mcp-tools-search'), {
      target: { value: 'missing tool' },
    });
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getByText('No tools match “missing tool”.')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('mcp-tools-search-clear'));
    expect(mocks.useMcpTools).toHaveBeenCalledWith('server-id', {
      limit: 25,
      offset: 0,
      q: '',
    });
    expect(
      screen.getByText('No tools have been discovered. Refresh the tool inventory.'),
    ).toBeInTheDocument();
  });
});
