import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ApiError } from '@/services/api/errors';
import { McpServerDialog } from './McpServerDialog';

const createServer = vi.fn();
const startOauth = vi.fn();
const resetCreate = vi.fn();
const resetOauth = vi.fn();
const toastError = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

vi.mock('../hooks/useMcpQueries', () => ({
  useCreateMcpServer: () => ({
    mutateAsync: createServer,
    isPending: false,
    reset: resetCreate,
  }),
  useStartMcpOauth: () => ({
    mutateAsync: startOauth,
    isPending: false,
    reset: resetOauth,
  }),
}));

function renderDialog(onOpenChange = vi.fn()) {
  return {
    onOpenChange,
    ...render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <McpServerDialog open onOpenChange={onOpenChange} />
        </MemoryRouter>
      </I18nextProvider>,
    ),
  };
}

async function chooseSelect(testId: string, option: string) {
  const trigger = screen.getByTestId(testId);
  fireEvent.keyDown(trigger, { key: 'Enter' });
  const item = await screen.findByRole('option', { name: option });
  fireEvent.click(item);
  await waitFor(() => expect(trigger).toHaveTextContent(option));
}

describe('McpServerDialog', () => {
  beforeAll(() => {
    Object.defineProperties(HTMLElement.prototype, {
      hasPointerCapture: {
        configurable: true,
        value: () => false,
      },
      releasePointerCapture: {
        configurable: true,
        value: () => undefined,
      },
      setPointerCapture: {
        configurable: true,
        value: () => undefined,
      },
      scrollIntoView: {
        configurable: true,
        value: () => undefined,
      },
    });
  });

  beforeEach(async () => {
    createServer.mockReset();
    startOauth.mockReset();
    resetCreate.mockReset();
    resetOauth.mockReset();
    toastError.mockReset();
    createServer.mockResolvedValue({
      id: 'figma-connection',
      display_name: 'Figma',
      status: 'connecting',
      health: 'unknown',
      auth: { mode: 'oauth', strategy: 'dynamic_registration' },
    });
    startOauth.mockRejectedValue(
      new ApiError('provider rejected registration', {
        status: 403,
        code: 'mcp_oauth_client_registration_failed',
      }),
    );
    await i18n.changeLanguage('en');
  });

  it('closes after persistence when OAuth bootstrap fails', async () => {
    const { onOpenChange } = renderDialog();
    fireEvent.change(screen.getByLabelText(i18n.t('apps.mcp.displayName')), {
      target: { value: 'Figma' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('apps.mcp.serverUrl')), {
      target: { value: 'https://mcp.figma.com/mcp' },
    });
    await chooseSelect('mcp-auth-mode', i18n.t('apps.mcp.auth.oauth'));
    await chooseSelect(
      'mcp-oauth-strategy',
      i18n.t('apps.mcp.oauth.dynamic'),
    );
    fireEvent.click(screen.getByTestId('mcp-shared-account-ack'));
    fireEvent.click(screen.getByTestId('mcp-server-submit'));

    await waitFor(() => {
      expect(createServer).toHaveBeenCalledTimes(1);
      expect(startOauth).toHaveBeenCalledWith({
        connectionId: 'figma-connection',
        returnPath: '/apps/mcp',
      });
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toastError).toHaveBeenCalledWith(
      expect.stringContaining('server was saved'),
    );
    expect(toastError).toHaveBeenCalledWith(
      expect.stringContaining('pre-approved'),
    );
  });

  it('submits at most once while creation is unresolved', async () => {
    let resolveCreate!: (server: {
      id: string;
      display_name: string;
      status: string;
      health: string;
      auth: { mode: 'none' };
    }) => void;
    createServer.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const { onOpenChange } = renderDialog();
    fireEvent.change(screen.getByLabelText(i18n.t('apps.mcp.displayName')), {
      target: { value: 'Public server' },
    });
    fireEvent.change(screen.getByLabelText(i18n.t('apps.mcp.serverUrl')), {
      target: { value: 'https://mcp.example.com/mcp' },
    });
    fireEvent.click(screen.getByTestId('mcp-shared-account-ack'));

    const submit = screen.getByTestId('mcp-server-submit');
    fireEvent.click(submit);
    fireEvent.click(submit);

    expect(createServer).toHaveBeenCalledTimes(1);
    resolveCreate({
      id: 'public-connection',
      display_name: 'Public server',
      status: 'active',
      health: 'unknown',
      auth: { mode: 'none' },
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
