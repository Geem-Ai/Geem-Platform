import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { ApiKey, CreatedApiKey } from '@/services/api/api-keys';
import type { AgentsAiUsage } from '@/services/api/apps';
import { ApiKeysPage } from './ApiKeysPage';

const workspaceState = { id: 'ws-a', role: 'owner' as string, permissions: [] as string[] };

const { useAgentsAiUsage } = vi.hoisted(() => ({
  useAgentsAiUsage: vi.fn(),
}));

vi.mock('@/features/apps/hooks/useAppsQueries', () => ({
  useAgentsAiUsage: (...args: unknown[]) => useAgentsAiUsage(...args),
}));

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: workspaceState.id,
      name: 'Acme',
      slug: 'acme',
      role: workspaceState.role,
      permissions: workspaceState.permissions,
    },
    currentMembership: {
      id: 'm1',
      workspace_id: workspaceState.id,
      user_id: 'u1',
      role: workspaceState.role,
      created_at: '2026-01-01T00:00:00Z',
      permissions: workspaceState.permissions,
    },
  }),
}));

vi.mock('@/lib/clipboard', () => ({
  copyText: vi.fn(async () => true),
}));

vi.mock('@/services/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/client')>(
    '@/services/api/client',
  );
  return {
    ...actual,
    getApiBaseUrl: () => 'https://api.geem.ai',
  };
});

const listApiKeys = vi.fn();
const createApiKey = vi.fn();
const revokeApiKey = vi.fn();

vi.mock('@/services/api/api-keys', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/api-keys')>(
    '@/services/api/api-keys',
  );
  return {
    ...actual,
    listApiKeys: () => listApiKeys(),
    createApiKey: (input: unknown) => createApiKey(input),
    revokeApiKey: (id: string) => revokeApiKey(id),
  };
});

function key(partial: Partial<ApiKey> = {}): ApiKey {
  return {
    id: 'key-1',
    workspace_id: workspaceState.id,
    name: 'Production',
    prefix: 'geem_sk_abcd1234',
    last_four: 'wxyz',
    scopes: ['chat:write'],
    created_by: 'u1',
    last_used_at: null,
    expires_at: null,
    revoked_at: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    ...partial,
  };
}

function agentsUsage(active: boolean): AgentsAiUsage {
  return {
    access: {
      status: active ? 'active' : 'not_entitled',
      plan_id: active ? 'agents-plan' : null,
      plan_code: active ? 'agents-team' : null,
      plan_name: active ? 'Agents Team' : null,
      plan_price_amount: active ? '199.00' : null,
      plan_currency: active ? 'SAR' : null,
      plan_billing_interval: active ? 'monthly' : null,
      current_period_start: active ? '2026-08-01T00:00:00Z' : null,
      current_period_end: active ? '2026-09-01T00:00:00Z' : null,
      commercially_entitled: active,
      installed: active,
    },
    agent_requests_daily: {
      used: 0,
      limit: active ? 100 : 0,
      reset_at: '2026-08-26T00:00:00Z',
    },
    base_url: 'https://api.geem.ai/api/v1/agent',
    model: 'dalseen/geem-1.0',
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <ApiKeysPage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('ApiKeysPage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    workspaceState.role = 'owner';
    workspaceState.permissions = [];
    listApiKeys.mockReset();
    createApiKey.mockReset();
    revokeApiKey.mockReset();
    useAgentsAiUsage.mockReset();
    useAgentsAiUsage.mockReturnValue({
      data: agentsUsage(false),
      isLoading: false,
      isError: false,
      error: null,
    });
    listApiKeys.mockResolvedValue([key()]);
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('lists keys with safe prefix and no plaintext secret', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-keys-list')).toBeInTheDocument();
    });
    expect(screen.getByText('Production')).toBeInTheDocument();
    expect(screen.getByText(/geem_sk_abcd1234••••wxyz/)).toBeInTheDocument();
    expect(screen.queryByText(/geem_sk_[a-zA-Z0-9_-]{20,}/)).not.toBeInTheDocument();
    expect(screen.getByTestId('api-key-status-active')).toBeInTheDocument();
  });

  it('localizes the independent Agents AI scope in the key list', async () => {
    listApiKeys.mockResolvedValue([
      key({ scopes: ['chat:write', 'agent:write'] }),
    ]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-keys-list')).toBeInTheDocument();
    });
    expect(screen.getByText(i18n.t('apiKeys.scopeAgentShort'))).toBeInTheDocument();
  });

  it('shows empty state for owners', async () => {
    listApiKeys.mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-keys-empty')).toBeInTheDocument();
    });
    expect(screen.getByText('No API keys yet')).toBeInTheDocument();
  });

  it('hides create for members', async () => {
    workspaceState.role = 'member';
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-keys-forbidden')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('create-api-key')).not.toBeInTheDocument();
    expect(listApiKeys).not.toHaveBeenCalled();
  });

  it('lets admin create and shows the plaintext secret once', async () => {
    workspaceState.role = 'admin';
    workspaceState.permissions = [
      'api_keys.view',
      'api_keys.create',
      'api_keys.revoke',
    ];
    listApiKeys.mockResolvedValue([]);
    const created: CreatedApiKey = {
      ...key({ id: 'key-new', name: 'Staging' }),
      key: 'geem_sk_once-only-secret-value-xxxxxxxx',
    };
    createApiKey.mockResolvedValue(created);
    const { client } = renderPage();
    await waitFor(() => screen.getByTestId('create-api-key'));
    fireEvent.click(screen.getByTestId('create-api-key'));
    fireEvent.change(screen.getByTestId('api-key-name-input'), {
      target: { value: 'Staging' },
    });
    fireEvent.click(screen.getByTestId('create-api-key-submit'));
    await waitFor(() => {
      expect(createApiKey).toHaveBeenCalledWith({
        name: 'Staging',
        scopes: ['chat:write'],
        expires_at: null,
      });
    });
    expect(screen.getByTestId('created-api-key-secret')).toHaveTextContent(
      'geem_sk_once-only-secret-value-xxxxxxxx',
    );
    fireEvent.click(screen.getByTestId('copy-api-key'));
    const { copyText } = await import('@/lib/clipboard');
    expect(copyText).toHaveBeenCalledWith('geem_sk_once-only-secret-value-xxxxxxxx');

    fireEvent.click(screen.getByText('Done'));
    await waitFor(() => {
      expect(screen.queryByTestId('created-api-key-secret')).not.toBeInTheDocument();
    });
    const cached = client.getQueryData(queryKeys.apiKeys('ws-a')) as ApiKey[] | undefined;
    expect(JSON.stringify(cached ?? [])).not.toContain('geem_sk_once-only-secret-value-xxxxxxxx');
  });

  it('adds agent:write only when the active-access checkbox is explicitly selected', async () => {
    listApiKeys.mockResolvedValue([]);
    useAgentsAiUsage.mockReturnValue({
      data: agentsUsage(true),
      isLoading: false,
      isError: false,
      error: null,
    });
    createApiKey.mockResolvedValue({
      ...key({ id: 'key-agent', name: 'Agent runtime', scopes: ['chat:write', 'agent:write'] }),
      key: 'geem_sk_agent-secret-once',
    });

    renderPage();
    fireEvent.click(await screen.findByTestId('create-api-key'));
    const scope = await screen.findByTestId('api-key-agent-scope');
    expect(scope).toBeEnabled();
    expect(scope).not.toBeChecked();
    fireEvent.click(scope);
    fireEvent.change(screen.getByTestId('api-key-name-input'), {
      target: { value: 'Agent runtime' },
    });
    fireEvent.click(screen.getByTestId('create-api-key-submit'));

    await waitFor(() => {
      expect(createApiKey).toHaveBeenCalledWith({
        name: 'Agent runtime',
        scopes: ['chat:write', 'agent:write'],
        expires_at: null,
      });
    });
  });

  it('keeps agent:write disabled without active installed access', async () => {
    listApiKeys.mockResolvedValue([]);
    renderPage();
    fireEvent.click(await screen.findByTestId('create-api-key'));
    expect(await screen.findByTestId('api-key-agent-scope')).toBeDisabled();
    expect(screen.getByTestId('api-key-agent-scope-gate')).toHaveTextContent(
      i18n.t('apiKeys.scopeAgentAccessRequired'),
    );
    expect(screen.getByRole('link', { name: i18n.t('apiKeys.manageAgentsAi') })).toHaveAttribute(
      'href',
      '/apps/agents-ai',
    );
  });

  it('validates name before submit', async () => {
    listApiKeys.mockResolvedValue([]);
    renderPage();
    await waitFor(() => screen.getByTestId('create-api-key'));
    fireEvent.click(screen.getByTestId('create-api-key'));
    fireEvent.click(screen.getByTestId('create-api-key-submit'));
    expect(createApiKey).not.toHaveBeenCalled();
    expect(screen.getByTestId('create-api-key-error')).toHaveTextContent('Name is required.');
  });

  it('revokes an active key', async () => {
    revokeApiKey.mockResolvedValue(key({ revoked_at: '2026-08-13T00:00:00Z' }));
    renderPage();
    await waitFor(() => screen.getByTestId('revoke-api-key-key-1'));
    fireEvent.click(screen.getByTestId('revoke-api-key-key-1'));
    expect(screen.getByTestId('revoke-api-key-dialog')).toHaveTextContent('Production');
    expect(screen.getByTestId('revoke-api-key-dialog').textContent).not.toMatch(
      /geem_sk_[a-zA-Z0-9_-]{20,}/,
    );
    fireEvent.click(screen.getByTestId('revoke-api-key-confirm'));
    await waitFor(() => {
      expect(revokeApiKey).toHaveBeenCalledWith('key-1');
    });
  });

  it('does not leak workspace A keys after switching to B', async () => {
    listApiKeys.mockImplementation(async () => {
      if (workspaceState.id === 'ws-a') return [key({ name: 'Alpha Key' })];
      return [key({ id: 'key-b', name: 'Beta Key', prefix: 'geem_sk_bbbbbbbb' })];
    });
    const { rerender, client } = renderPage();
    await waitFor(() => expect(screen.getByText('Alpha Key')).toBeInTheDocument());
    expect(queryKeys.apiKeys('ws-a')[1]).toBe('ws-a');

    workspaceState.id = 'ws-b';
    rerender(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <ApiKeysPage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('Beta Key')).toBeInTheDocument());
    expect(screen.queryByText('Alpha Key')).not.toBeInTheDocument();
  });

  it('renders LTR curl with placeholder credentials', async () => {
    renderPage();
    await waitFor(() => screen.getByTestId('open-api-quick-start'));
    expect(screen.queryByTestId('api-quick-start-curl')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('open-api-quick-start'));
    await waitFor(() => screen.getByTestId('api-quick-start-curl'));
    const curl = screen.getByTestId('api-quick-start-curl');
    expect(curl).toHaveAttribute('dir', 'ltr');
    expect(curl.textContent).toContain('POST "https://api.geem.ai/api/v1/chat/completions"');
    expect(curl.textContent).toContain('YOUR_API_KEY');
    expect(curl.textContent).toContain('X-Geem-Expert-Id: YOUR_EXPERT_ID');
    expect(curl.textContent).toContain('"stream": false');
    expect(screen.getByTestId('api-quick-start-stream').textContent).toContain(
      '"stream": true',
    );

    fireEvent.click(screen.getByTestId('api-quick-start-curl-copy'));
    const { copyText } = await import('@/lib/clipboard');
    const copyMock = copyText as unknown as ReturnType<typeof vi.fn>;
    expect(copyMock).toHaveBeenCalled();
    const curlCopied = copyMock.mock.calls[copyMock.mock.calls.length - 1]?.[0];
    expect(String(curlCopied ?? '')).toContain('YOUR_API_KEY');

    fireEvent.click(screen.getByTestId('api-quick-start-stream-copy'));
    const streamCopied = copyMock.mock.calls[copyMock.mock.calls.length - 1]?.[0];
    expect(String(streamCopied ?? '')).toContain('"stream": true');
  });

  it('shows revoked and expired badges', async () => {
    listApiKeys.mockResolvedValue([
      key({ id: 'r', name: 'Old', revoked_at: '2026-08-01T00:00:00Z' }),
      key({
        id: 'e',
        name: 'Stale',
        expires_at: '2020-01-01T00:00:00Z',
      }),
    ]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('api-key-status-revoked')).toBeInTheDocument();
      expect(screen.getByTestId('api-key-status-expired')).toBeInTheDocument();
    });
  });
});
