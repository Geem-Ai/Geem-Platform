import { act } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import en from '@/locales/en.json';
import ar from '@/locales/ar.json';
import type { CatalogApp, WhatsAppConnection } from '@/services/api/apps';
import { AppConnectionsPanel } from '@/features/apps/connections/components/AppConnectionsPanel';
import { WhatsAppConnectDialog } from './components/WhatsAppConnectDialog';
import { WhatsAppPairingCodeStep } from './components/WhatsAppPairingCodeStep';
import { WhatsAppQrStep } from './components/WhatsAppQrStep';

const workspaceState = { id: 'ws-a', role: 'owner' };

const {
  useAppConnections,
  useConnectionSyncRuns,
  useDisconnectConnection,
  useHealthCheckConnection,
  useRequestConnectionSync,
  useStartConnection,
  getWhatsAppStatus,
  getWhatsAppQr,
  requestWhatsAppPairingCode,
  startWhatsAppConnection,
  useExperts,
  copyText,
} = vi.hoisted(() => ({
  useAppConnections: vi.fn(),
  useConnectionSyncRuns: vi.fn(),
  useDisconnectConnection: vi.fn(),
  useHealthCheckConnection: vi.fn(),
  useRequestConnectionSync: vi.fn(),
  useStartConnection: vi.fn(),
  getWhatsAppStatus: vi.fn(),
  getWhatsAppQr: vi.fn(),
  requestWhatsAppPairingCode: vi.fn(),
  startWhatsAppConnection: vi.fn(),
  useExperts: vi.fn(),
  copyText: vi.fn(),
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

vi.mock('@/features/apps/connections/hooks/useConnectionQueries', () => ({
  useAppConnections: (...args: unknown[]) => useAppConnections(...args),
  useConnectionSyncRuns: (...args: unknown[]) => useConnectionSyncRuns(...args),
  useDisconnectConnection: () => useDisconnectConnection(),
  useHealthCheckConnection: () => useHealthCheckConnection(),
  useRequestConnectionSync: () => useRequestConnectionSync(),
  useStartConnection: () => useStartConnection(),
}));

vi.mock('@/services/api/apps', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/apps')>(
    '@/services/api/apps',
  );
  return {
    ...actual,
    getWhatsAppStatus: (...args: unknown[]) => getWhatsAppStatus(...args),
    getWhatsAppQr: (...args: unknown[]) => getWhatsAppQr(...args),
    requestWhatsAppPairingCode: (...args: unknown[]) =>
      requestWhatsAppPairingCode(...args),
    startWhatsAppConnection: (...args: unknown[]) => startWhatsAppConnection(...args),
  };
});

vi.mock('@/features/experts/hooks/useExperts', () => ({
  useExperts: () => useExperts(),
}));

vi.mock('@/lib/clipboard', () => ({
  copyText: (...args: unknown[]) => copyText(...args),
}));

function catalogApp(partial: Partial<CatalogApp> = {}): CatalogApp {
  return {
    id: 'app-1',
    slug: 'whatsapp',
    name: 'WhatsApp',
    short_description: 'Connect WhatsApp',
    description: 'Full',
    category: {
      slug: 'communication',
      name_key: 'apps.categories.communication',
      description_key: null,
      icon: null,
      sort_order: 10,
    },
    icon_url: null,
    billing_type: 'subscription',
    status: 'published',
    is_featured: true,
    sort_order: 10,
    plans: [
      {
        id: 'plan-1',
        code: 'monthly',
        name: 'Monthly',
        description: null,
        billing_interval: 'monthly',
        price_amount: '9.00',
        currency: 'SAR',
        is_default: true,
        entitlements: { connections: 1 },
      },
    ],
    installation: {
      id: 'inst-1',
      status: 'active',
      installed_at: '2026-01-01T00:00:00Z',
    },
    installation_status: 'active',
    can_install: false,
    can_uninstall: true,
    access_requirement: 'subscription',
    access: {
      status: 'active',
      plan_id: 'plan-1',
      plan_code: 'monthly',
      plan_name: 'Monthly',
      current_period_start: '2026-01-01T00:00:00Z',
      current_period_end: '2026-02-01T00:00:00Z',
      commercially_entitled: true,
      can_purchase: false,
      can_renew: false,
      can_install: false,
      can_uninstall: true,
    },
    connector: {
      key: 'openwa',
      kind: 'channel',
      available: true,
      auth_mode: 'custom',
      can_connect: true,
      supports_sync: false,
      supports_webhooks: true,
      supports_health_check: true,
    },
    has_active_connection: false,
    ...partial,
  };
}

function connection(partial: Partial<WhatsAppConnection> = {}): WhatsAppConnection {
  return {
    id: 'conn-1',
    workspace_id: 'ws-a',
    app_installation_id: 'inst-1',
    app_slug: 'whatsapp',
    connector_key: 'openwa',
    connector_kind: 'channel',
    display_name: 'Sales Line',
    external_account_id: '966500000000',
    external_account_name: 'Sales',
    auth_mode: 'custom',
    status: 'connecting',
    health: 'unknown',
    connected_at: null,
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
      can_health_check: false,
      can_sync: false,
      can_reconnect: true,
    },
    provider_status: 'qr_ready',
    connect_mode: 'qr',
    phone: '966500000000',
    expert_id: 'exp-1',
    enabled: true,
    auto_reply_enabled: true,
    respond_to_groups: false,
    ...partial,
  };
}

function renderWithProviders(node: React.ReactNode) {
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>
    </I18nextProvider>,
  );
}

describe('WhatsApp Phase 9F UI', () => {
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
      error: null,
    });
    useHealthCheckConnection.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
    });
    useRequestConnectionSync.mockReturnValue({
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
    useExperts.mockReturnValue({
      data: [{ id: 'exp-1', name: 'Expert A', status: 'active' }],
      isLoading: false,
    });
    getWhatsAppStatus.mockResolvedValue(
      connection({ provider_status: 'ready', status: 'active' }),
    );
    getWhatsAppQr.mockResolvedValue({
      status: 'qr_ready',
      qr_code: 'data:image/png;base64,abc',
    });
    requestWhatsAppPairingCode.mockResolvedValue({
      status: 'qr_ready',
      pairing_code: 'ABCD1234',
    });
    startWhatsAppConnection.mockResolvedValue(connection());
    copyText.mockResolvedValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('connect opens modal with QR and pairing options', () => {
    renderWithProviders(<AppConnectionsPanel app={catalogApp()} canManage />);

    fireEvent.click(screen.getByTestId('connection-connect'));

    expect(screen.getByTestId('whatsapp-connect-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('whatsapp-option-qr')).toBeInTheDocument();
    expect(screen.getByTestId('whatsapp-option-pairing')).toBeInTheDocument();
  });

  it('QR step renders returned data URL', async () => {
    getWhatsAppStatus.mockResolvedValue(
      connection({ provider_status: 'qr_ready', status: 'connecting' }),
    );

    renderWithProviders(
      <WhatsAppQrStep appSlug="whatsapp" initialConnection={connection()} />,
    );

    const image = await screen.findByTestId('whatsapp-qr-image');
    expect(image).toHaveAttribute('src', 'data:image/png;base64,abc');
  });

  it('pairing code renders and copies', async () => {
    getWhatsAppStatus.mockResolvedValue(
      connection({
        connect_mode: 'pairing',
        provider_status: 'qr_ready',
        status: 'connecting',
      }),
    );

    renderWithProviders(
      <WhatsAppPairingCodeStep
        appSlug="whatsapp"
        initialConnection={connection({
          connect_mode: 'pairing',
          provider_status: 'qr_ready',
          status: 'connecting',
        })}
      />,
    );

    fireEvent.change(screen.getByTestId('whatsapp-phone-input'), {
      target: { value: '+966 50 000 0000' },
    });
    fireEvent.click(screen.getByTestId('whatsapp-request-pairing'));

    expect(await screen.findByTestId('whatsapp-pairing-code')).toHaveTextContent(
      'ABCD 1234',
    );

    fireEvent.click(screen.getByTestId('whatsapp-copy-pairing'));
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('ABCD1234'));
  });

  it(
    'polling stops after ready',
    async () => {
      vi.useRealTimers();
      getWhatsAppStatus.mockResolvedValue(
        connection({ provider_status: 'ready', status: 'active' }),
      );

      renderWithProviders(
        <WhatsAppQrStep
          appSlug="whatsapp"
          initialConnection={connection({
            provider_status: 'initializing',
            status: 'connecting',
          })}
        />,
      );

      await waitFor(() => expect(getWhatsAppStatus).toHaveBeenCalledTimes(1));
      await waitFor(() =>
        expect(screen.getByTestId('whatsapp-status-connected')).toBeInTheDocument(),
      );

      const callsAfterReady = getWhatsAppStatus.mock.calls.length;
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
      expect(getWhatsAppStatus).toHaveBeenCalledTimes(callsAfterReady);
    },
    10000,
  );

  it('shows member read-only state', async () => {
    workspaceState.role = 'member';
    useAppConnections.mockReturnValue({
      data: {
        items: [connection({ status: 'active', provider_status: 'ready' })],
        total: 1,
        limit: 50,
        offset: 0,
      },
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithProviders(<AppConnectionsPanel app={catalogApp()} canManage={false} />);

    expect(await screen.findByTestId('whatsapp-member-readonly')).toBeInTheDocument();
    expect(screen.getByTestId('whatsapp-expert-select')).toBeDisabled();
    expect(screen.queryByTestId('whatsapp-disconnect')).not.toBeInTheDocument();
  });

  it('disables connect another when the connection limit is reached', async () => {
    useAppConnections.mockReturnValue({
      data: {
        items: [connection({ status: 'active', provider_status: 'ready' })],
        total: 1,
        limit: 50,
        offset: 0,
      },
      isLoading: false,
      isError: false,
      error: null,
    });

    renderWithProviders(<AppConnectionsPanel app={catalogApp()} canManage />);

    expect(await screen.findByTestId('whatsapp-connect-another')).toBeDisabled();
    expect(screen.getByTestId('whatsapp-limit-reached')).toBeInTheDocument();
  });

  it('EN and AR WhatsApp keys exist', () => {
    expect(en.apps.whatsapp.connect.qrTitle).toBeTruthy();
    expect(en.apps.whatsapp.status.connected).toBeTruthy();
    expect(ar.apps.whatsapp.connect.qrTitle).toBeTruthy();
    expect(ar.apps.whatsapp.status.connected).toBeTruthy();
  });

  it('dialog can advance into QR and pairing steps', async () => {
    renderWithProviders(
      <WhatsAppConnectDialog appSlug="whatsapp" open onOpenChange={vi.fn()} />,
    );

    fireEvent.click(screen.getByTestId('whatsapp-option-qr'));
    expect(await screen.findByTestId('whatsapp-qr-step')).toBeInTheDocument();

    renderWithProviders(
      <WhatsAppConnectDialog appSlug="whatsapp" open onOpenChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('whatsapp-option-pairing'));
    expect(await screen.findByTestId('whatsapp-pairing-step')).toBeInTheDocument();
  });
});
