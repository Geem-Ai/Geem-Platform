import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { AppConnection, CatalogApp, ConnectorSyncRun } from '@/services/api/apps';
import { AppConnectionsPanel } from './components/AppConnectionsPanel';
import { ConnectionStatusBadge } from './components/ConnectionStatusBadge';
import { SyncHistory } from './components/SyncHistory';
import { InstalledAppCard } from '../components/InstalledAppCard';

const workspaceState = { id: 'ws-a', role: 'owner' };

const { useAppConnections, useConnectionSyncRuns, useDisconnectConnection, useStartConnection } =
  vi.hoisted(() => ({
    useAppConnections: vi.fn(),
    useConnectionSyncRuns: vi.fn(),
    useDisconnectConnection: vi.fn(),
    useStartConnection: vi.fn(),
    useHealthCheckConnection: vi.fn(),
    useRequestConnectionSync: vi.fn(),
  }));

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: workspaceState.id,
      name: 'Acme',
      slug: 'acme',
      role: workspaceState.role,
    },
    currentMembership: {
      id: 'm1',
      workspace_id: workspaceState.id,
      user_id: 'u1',
      role: workspaceState.role,
      created_at: '2026-01-01T00:00:00Z',
    },
  }),
}));

vi.mock('./hooks/useConnectionQueries', () => ({
  useAppConnections: (...args: unknown[]) => useAppConnections(...args),
  useConnectionSyncRuns: (...args: unknown[]) => useConnectionSyncRuns(...args),
  useDisconnectConnection: () => useDisconnectConnection(),
  useStartConnection: () => useStartConnection(),
  useHealthCheckConnection: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useRequestConnectionSync: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
}));

vi.mock('../hooks/useAppsQueries', () => ({
  useInstallApp: () => ({ mutate: vi.fn(), isPending: false }),
  useUninstallApp: () => ({ mutate: vi.fn(), isPending: false }),
}));

function catalogApp(partial: Partial<CatalogApp> = {}): CatalogApp {
  return {
    id: 'app-1',
    slug: 'google-drive',
    name: 'Google Drive',
    short_description: 'Connect Drive',
    description: 'Full',
    category: {
      slug: 'knowledge',
      name_key: 'apps.categories.knowledge',
      description_key: null,
      icon: null,
      sort_order: 10,
    },
    icon_url: null,
    billing_type: 'free',
    status: 'published',
    is_featured: true,
    sort_order: 10,
    plans: [],
    installation: {
      id: 'inst-1',
      status: 'active',
      installed_at: '2026-01-01T00:00:00Z',
    },
    installation_status: 'active',
    can_install: false,
    can_uninstall: true,
    access_requirement: 'free',
    access: {
      status: 'active',
      plan_id: 'plan-1',
      plan_code: 'free',
      plan_name: 'Free',
      current_period_start: null,
      current_period_end: null,
      commercially_entitled: true,
      can_purchase: false,
      can_renew: false,
      can_install: false,
      can_uninstall: true,
    },
    connector: {
      key: 'google_drive',
      kind: 'knowledge_source',
      available: false,
      auth_mode: null,
      can_connect: false,
      supports_sync: false,
      supports_webhooks: false,
      supports_health_check: false,
    },
    has_active_connection: false,
    ...partial,
  };
}

function connection(partial: Partial<AppConnection> = {}): AppConnection {
  return {
    id: 'conn-1',
    workspace_id: 'ws-a',
    app_installation_id: 'inst-1',
    app_slug: 'google-drive',
    connector_key: 'google_drive',
    connector_kind: 'knowledge_source',
    display_name: 'Work Drive',
    external_account_id: 'ext-1',
    external_account_name: 'Example',
    auth_mode: 'oauth2',
    status: 'active',
    health: 'healthy',
    connected_at: '2026-01-02T00:00:00Z',
    disconnected_at: null,
    last_health_check_at: null,
    last_success_at: null,
    last_error_code: null,
    last_error_message: null,
    last_error_at: null,
    credentials_expires_at: null,
    created_at: '2026-01-02T00:00:00Z',
    capabilities: {
      can_disconnect: true,
      can_health_check: true,
      can_sync: false,
      can_reconnect: false,
    },
    ...partial,
  };
}

describe('Phase 9C connection UI', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    workspaceState.role = 'owner';
    await i18n.changeLanguage('en');
    useAppConnections.mockReturnValue({
      data: { items: [], total: 0, limit: 50, offset: 0 },
      isLoading: false,
      isError: false,
      error: null,
    });
    useConnectionSyncRuns.mockReturnValue({
      data: { items: [], total: 0, limit: 50, offset: 0 },
      isLoading: false,
    });
    useDisconnectConnection.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    });
    useStartConnection.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('shows connector unavailable when adapter is not ready', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={new QueryClient()}>
          <AppConnectionsPanel app={catalogApp()} canManage />
        </QueryClientProvider>
      </I18nextProvider>,
    );
    expect(screen.getByTestId('connector-unavailable')).toBeInTheDocument();
    expect(screen.getByText(/not available yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Not connected/i)).toBeInTheDocument();
  });

  it('distinguishes installed vs connected on installed cards', () => {
    const app = catalogApp({ has_active_connection: false });
    render(
      <MemoryRouter>
        <I18nextProvider i18n={i18n}>
          <QueryClientProvider client={new QueryClient()}>
            <InstalledAppCard
              installation={{
                id: 'inst-1',
                workspace_id: 'ws-a',
                app_id: 'app-1',
                status: 'active',
                installed_at: '2026-01-01T00:00:00Z',
                uninstalled_at: null,
                installed_by_user_id: null,
                app,
              }}
              canManage
            />
          </QueryClientProvider>
        </I18nextProvider>
      </MemoryRouter>,
    );
    expect(screen.getByText('Installed')).toBeInTheDocument();
    expect(screen.getByText('Not connected')).toBeInTheDocument();
    expect(screen.getByText(/available soon/i)).toBeInTheDocument();
  });

  it('renders connection status badges', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ConnectionStatusBadge status="active" />
        <ConnectionStatusBadge status="disconnected" />
        <ConnectionStatusBadge status="degraded" />
      </I18nextProvider>,
    );
    expect(screen.getByTestId('connection-status-active')).toHaveTextContent(
      'Connected',
    );
    expect(
      screen.getByTestId('connection-status-disconnected'),
    ).toHaveTextContent('Disconnected');
    expect(screen.getByTestId('connection-status-degraded')).toHaveTextContent(
      'Degraded',
    );
  });

  it('shows sync history empty state', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <SyncHistory runs={[]} />
      </I18nextProvider>,
    );
    expect(screen.getByTestId('sync-history-empty')).toBeInTheDocument();
  });

  it('renders sync runs', () => {
    const run: ConnectorSyncRun = {
      id: 'run-1',
      workspace_id: 'ws-a',
      app_connection_id: 'conn-1',
      trigger: 'manual',
      status: 'succeeded',
      started_at: '2026-01-02T00:00:00Z',
      completed_at: '2026-01-02T00:01:00Z',
      items_seen: 3,
      items_created: 2,
      items_updated: 1,
      items_deleted: 0,
      items_failed: 0,
      error_code: null,
      error_message: null,
      created_by_user_id: null,
      created_at: '2026-01-02T00:00:00Z',
    };
    render(
      <I18nextProvider i18n={i18n}>
        <SyncHistory runs={[run]} />
      </I18nextProvider>,
    );
    expect(screen.getByTestId('sync-run-run-1')).toBeInTheDocument();
    expect(screen.getByText(/Manual sync/i)).toBeInTheDocument();
  });

  it('hides technical sync error dumps behind a friendly message', () => {
    const run: ConnectorSyncRun = {
      id: 'run-fail',
      workspace_id: 'ws-a',
      app_connection_id: 'conn-1',
      trigger: 'initial',
      status: 'failed',
      started_at: '2026-01-02T00:00:00Z',
      completed_at: '2026-01-02T00:01:00Z',
      items_seen: 0,
      items_created: 0,
      items_updated: 0,
      items_deleted: 0,
      items_failed: 1,
      error_code: 'connector_connection_failed',
      error_message:
        '(psycopg.errors.CheckViolation) new row for relation "storage_usage_events" violates check constraint',
      created_by_user_id: null,
      created_at: '2026-01-02T00:00:00Z',
    };
    render(
      <I18nextProvider i18n={i18n}>
        <SyncHistory runs={[run]} />
      </I18nextProvider>,
    );
    expect(screen.queryByText(/psycopg/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/CheckViolation/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Could not complete this sync/i),
    ).toBeInTheDocument();
  });

  it('scopes connection query keys by workspace', () => {
    const a = queryKeys.appConnections('ws-a', 'google-drive');
    const b = queryKeys.appConnections('ws-b', 'google-drive');
    expect(a).not.toEqual(b);
    expect(a).toEqual(
      expect.arrayContaining(['ws-a', 'apps', 'connections', 'google-drive']),
    );
  });

  it('shows connect when adapter is available and empty', async () => {
    const app = catalogApp({
      connector: {
        key: 'google_drive',
        kind: 'knowledge_source',
        available: true,
        auth_mode: 'oauth2',
        can_connect: true,
        supports_sync: true,
        supports_webhooks: false,
        supports_health_check: true,
      },
    });
    render(
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={new QueryClient()}>
          <AppConnectionsPanel app={app} canManage />
        </QueryClientProvider>
      </I18nextProvider>,
    );
    expect(await screen.findByTestId('connection-connect')).toBeInTheDocument();
  });

  it('hides disconnect for members', async () => {
    workspaceState.role = 'member';
    useAppConnections.mockReturnValue({
      data: {
        items: [
          connection({
            capabilities: {
              can_disconnect: false,
              can_health_check: false,
              can_sync: false,
              can_reconnect: false,
            },
          }),
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
      isLoading: false,
      isError: false,
      error: null,
    });
    const app = catalogApp({
      connector: {
        key: 'google_drive',
        kind: 'knowledge_source',
        available: true,
        auth_mode: 'oauth2',
        can_connect: true,
        supports_sync: true,
        supports_webhooks: false,
        supports_health_check: true,
      },
      has_active_connection: true,
    });
    render(
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={new QueryClient()}>
          <AppConnectionsPanel app={app} canManage={false} />
        </QueryClientProvider>
      </I18nextProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('connection-card-conn-1')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('connection-disconnect')).not.toBeInTheDocument();
  });

  it('supports Arabic connection labels', async () => {
    await i18n.changeLanguage('ar');
    render(
      <I18nextProvider i18n={i18n}>
        <ConnectionStatusBadge status="active" />
      </I18nextProvider>,
    );
    expect(screen.getByTestId('connection-status-active')).toHaveTextContent(
      'متصل',
    );
  });
});
