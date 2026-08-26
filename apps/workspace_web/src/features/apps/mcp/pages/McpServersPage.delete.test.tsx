import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ApiError } from '@/services/api/errors';
import type { McpServer } from '@/services/api/mcp';
import { McpServersPage } from './McpServersPage';

const mocks = vi.hoisted(() => ({
  deleteServer: vi.fn(),
  reauthorize: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

const server: McpServer = {
  id: 'server-id',
  display_name: 'Figma',
  endpoint_host: 'mcp.figma.com',
  auth: { mode: 'oauth', strategy: 'dynamic_registration' },
  status: 'error',
  health: 'failed',
};

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => mocks.toastError(...args),
    success: (...args: unknown[]) => mocks.toastSuccess(...args),
  },
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/authz/usePermissions', () => ({
  usePermissions: () => ({ can: () => true }),
}));

vi.mock('../components/McpServerDialog', () => ({
  McpServerDialog: () => null,
}));

vi.mock('../components/McpUsageSummary', () => ({
  McpUsageSummary: () => null,
}));

vi.mock('../hooks/useMcpQueries', () => ({
  useMcpServers: () => ({
    data: { items: [server], total: 1, limit: 100, offset: 0 },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useDeleteMcpServer: () => ({
    mutateAsync: mocks.deleteServer,
    isPending: false,
  }),
  useReauthorizeMcpServer: () => ({
    mutateAsync: mocks.reauthorize,
    isPending: false,
  }),
}));

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <McpServersPage />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('McpServersPage delete confirmation', () => {
  beforeEach(async () => {
    mocks.deleteServer.mockReset();
    mocks.reauthorize.mockReset();
    mocks.toastError.mockReset();
    mocks.toastSuccess.mockReset();
    mocks.deleteServer.mockResolvedValue(undefined);
    await i18n.changeLanguage('en');
  });

  it('opens a styled confirmation and cancels without deleting', async () => {
    const browserConfirm = vi.spyOn(window, 'confirm');
    renderPage();

    fireEvent.click(screen.getByTestId('mcp-delete-server-server-id'));
    expect(await screen.findByTestId('mcp-delete-dialog')).toHaveTextContent(
      'Figma',
    );
    expect(screen.getByTestId('mcp-delete-dialog')).toHaveTextContent(
      'mcp.figma.com',
    );
    expect(browserConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('mcp-delete-cancel'));
    await waitFor(() => {
      expect(screen.queryByTestId('mcp-delete-dialog')).not.toBeInTheDocument();
    });
    expect(mocks.deleteServer).not.toHaveBeenCalled();
    browserConfirm.mockRestore();
  });

  it('deletes the selected server after confirmation', async () => {
    renderPage();
    fireEvent.click(screen.getByTestId('mcp-delete-server-server-id'));
    fireEvent.click(await screen.findByTestId('mcp-delete-confirm'));

    await waitFor(() => {
      expect(mocks.deleteServer).toHaveBeenCalledWith('server-id');
      expect(mocks.toastSuccess).toHaveBeenCalledWith('MCP server deleted');
      expect(screen.queryByTestId('mcp-delete-dialog')).not.toBeInTheDocument();
    });
  });

  it('keeps the dialog open with an inline error when deletion fails', async () => {
    mocks.deleteServer.mockRejectedValue(
      new ApiError('provider unavailable', {
        status: 502,
        code: 'mcp_server_unreachable',
      }),
    );
    renderPage();
    fireEvent.click(screen.getByTestId('mcp-delete-server-server-id'));
    fireEvent.click(await screen.findByTestId('mcp-delete-confirm'));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The MCP server could not be reached safely.',
    );
    expect(screen.getByTestId('mcp-delete-dialog')).toBeInTheDocument();
    expect(mocks.toastError).toHaveBeenCalledWith(
      'The MCP server could not be reached safely.',
    );
  });
});
