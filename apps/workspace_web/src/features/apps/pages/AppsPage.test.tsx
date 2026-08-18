import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { CatalogApp, CatalogAppList } from '@/services/api/apps';
import { AppsPage } from './AppsPage';
import { InstalledAppsPage } from './InstalledAppsPage';
import { errorMessageKey } from '@/services/api/errors';
import { ApiError } from '@/services/api/errors';

const workspaceState = { id: 'ws-a', role: 'owner' };

const {
  useApps,
  useAppCategories,
  useApp,
  useAppInstallations,
  useInstallApp,
  useUninstallApp,
  useAppCheckout,
  useAppRenewal,
  installMutate,
  uninstallMutate,
  checkoutMutate,
  renewMutate,
} = vi.hoisted(() => {
  const installMutate = vi.fn();
  const uninstallMutate = vi.fn();
  const checkoutMutate = vi.fn();
  const renewMutate = vi.fn();
  return {
    useApps: vi.fn(),
    useAppCategories: vi.fn(),
    useApp: vi.fn(),
    useAppInstallations: vi.fn(),
    useInstallApp: vi.fn(),
    useUninstallApp: vi.fn(),
    useAppCheckout: vi.fn(),
    useAppRenewal: vi.fn(),
    installMutate,
    uninstallMutate,
    checkoutMutate,
    renewMutate,
  };
});

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

vi.mock('../hooks/useAppsQueries', () => ({
  useApps: (...args: unknown[]) => useApps(...args),
  useAppCategories: (...args: unknown[]) => useAppCategories(...args),
  useApp: (...args: unknown[]) => useApp(...args),
  useAppInstallations: (...args: unknown[]) => useAppInstallations(...args),
  useInstallApp: () => useInstallApp(),
  useUninstallApp: () => useUninstallApp(),
  useAppCheckout: () => useAppCheckout(),
  useAppRenewal: () => useAppRenewal(),
}));

vi.mock('../connections/hooks/useConnectionQueries', () => ({
  useAppConnections: () => ({
    data: { items: [], total: 0, limit: 50, offset: 0 },
    isLoading: false,
    isError: false,
    error: null,
  }),
  useConnectionSyncRuns: () => ({
    data: { items: [], total: 0, limit: 50, offset: 0 },
    isLoading: false,
  }),
  useDisconnectConnection: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  }),
  useStartConnection: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
  useHealthCheckConnection: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useRequestConnectionSync: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

function catalogApp(partial: Partial<CatalogApp> = {}): CatalogApp {
  return {
    id: 'app-1',
    slug: 'google-drive',
    name: 'Google Drive',
    short_description: 'Connect Drive',
    description: 'Full Drive description',
    category: {
      slug: 'knowledge',
      name_key: 'apps.categories.knowledge',
      description_key: null,
      icon: null,
      sort_order: 10,
    },
    icon_url: '/brand/apps/google-drive.svg',
    billing_type: 'free',
    status: 'published',
    is_featured: true,
    sort_order: 10,
    plans: [
      {
        id: 'plan-1',
        code: 'free',
        name: 'Free',
        description: null,
        billing_interval: 'none',
        price_amount: '0.00',
        currency: 'SAR',
        is_default: true,
        entitlements: {},
      },
    ],
    installation: null,
    installation_status: null,
    can_install: true,
    can_uninstall: false,
    access_requirement: 'free',
    access: {
      status: 'entitled_not_installed',
      plan_id: 'plan-1',
      plan_code: 'free',
      plan_name: 'Free',
      current_period_start: null,
      current_period_end: null,
      commercially_entitled: true,
      can_purchase: false,
      can_renew: false,
      can_install: true,
      can_uninstall: false,
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

function listResponse(items: CatalogApp[]): CatalogAppList {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function querySuccess<T>(data: T) {
  return {
    data,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  };
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/apps" element={<AppsPage />} />
              <Route path="/apps/installed" element={<InstalledAppsPage />} />
              <Route path="/apps/:slug" element={<AppsPage />} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

const starterApps = [
  catalogApp(),
  catalogApp({
    id: 'app-2',
    slug: 'microsoft-onedrive',
    name: 'Microsoft OneDrive',
    is_featured: true,
  }),
  catalogApp({
    id: 'app-3',
    slug: 'whatsapp',
    name: 'WhatsApp',
    billing_type: 'subscription',
    status: 'published',
    can_install: false,
    access_requirement: 'subscription',
    access: {
      status: 'not_entitled',
      plan_id: null,
      plan_code: null,
      plan_name: null,
      current_period_start: null,
      current_period_end: null,
      commercially_entitled: false,
      can_purchase: true,
      can_renew: false,
      can_install: false,
      can_uninstall: false,
    },
    category: {
      slug: 'communication',
      name_key: 'apps.categories.communication',
      description_key: null,
      icon: null,
      sort_order: 20,
    },
    plans: [
      {
        id: 'plan-line',
        code: 'line',
        name: 'WhatsApp Line',
        description: 'One connection',
        billing_interval: 'monthly',
        price_amount: '79.00',
        currency: 'SAR',
        is_default: true,
        entitlements: { connections: 1 },
      },
    ],
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
  }),
];

describe('Apps feature', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    workspaceState.role = 'owner';
    await i18n.changeLanguage('en');

    useAppCategories.mockReturnValue(
      querySuccess([
        {
          slug: 'knowledge',
          name_key: 'apps.categories.knowledge',
          description_key: null,
          icon: null,
          sort_order: 10,
        },
        {
          slug: 'communication',
          name_key: 'apps.categories.communication',
          description_key: null,
          icon: null,
          sort_order: 20,
        },
      ]),
    );
    useApps.mockReturnValue(querySuccess(listResponse(starterApps)));
    useAppInstallations.mockReturnValue(
      querySuccess({ items: [], total: 0, limit: 100, offset: 0 }),
    );
    useApp.mockImplementation((slug?: string) =>
      querySuccess(
        starterApps.find((a) => a.slug === slug) ?? catalogApp({ slug: slug ?? 'x' }),
      ),
    );
    installMutate.mockResolvedValue({});
    uninstallMutate.mockResolvedValue({});
    checkoutMutate.mockResolvedValue({
      purchase_id: 'p1',
      redirect_url: 'https://pay.example/app',
    });
    renewMutate.mockResolvedValue({
      purchase_id: 'p2',
      redirect_url: 'https://pay.example/renew',
    });
    useInstallApp.mockReturnValue({
      mutateAsync: installMutate,
      isPending: false,
    });
    useUninstallApp.mockReturnValue({
      mutateAsync: uninstallMutate,
      isPending: false,
    });
    useAppCheckout.mockReturnValue({
      mutateAsync: checkoutMutate,
      isPending: false,
    });
    useAppRenewal.mockReturnValue({
      mutateAsync: renewMutate,
      isPending: false,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders App Store with featured apps and free badge', async () => {
    renderAt('/apps');
    expect(await screen.findByTestId('apps-page')).toBeInTheDocument();
    expect(screen.getAllByTestId('app-card-google-drive').length).toBeGreaterThan(0);
    expect(screen.getByTestId('apps-featured')).toBeInTheDocument();
    expect(screen.getAllByText(i18n.t('apps.billing.free')).length).toBeGreaterThan(0);
  });

  it('filters by category', async () => {
    renderAt('/apps');
    await screen.findByTestId('apps-category-filter');
    fireEvent.click(
      screen.getByRole('tab', { name: i18n.t('apps.categories.communication') }),
    );
    await waitFor(() => {
      expect(useApps).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'communication' }),
      );
    });
  });

  it('opens side sheet when navigating to app slug', async () => {
    useApp.mockReturnValue(querySuccess(catalogApp()));
    renderAt('/apps/google-drive');
    expect(await screen.findByTestId('apps-page')).toBeInTheDocument();
    expect(await screen.findByTestId('app-detail-sheet')).toBeInTheDocument();
    expect(screen.getByTestId('app-install')).toBeInTheDocument();
  });

  it('shows coming soon on unavailable detail and blocks install', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'soon-tool',
          name: 'Soon Tool',
          billing_type: 'subscription',
          status: 'coming_soon',
          can_install: false,
          access_requirement: 'unavailable',
          access: {
            status: 'unavailable',
            plan_id: null,
            plan_code: null,
            plan_name: null,
            current_period_start: null,
            current_period_end: null,
            commercially_entitled: false,
            can_purchase: false,
            can_renew: false,
            can_install: false,
            can_uninstall: false,
          },
          plans: [],
          connector: null,
        }),
      ),
    );
    renderAt('/apps/soon-tool');
    const sheet = await screen.findByTestId('app-detail-sheet');
    expect(sheet).toBeInTheDocument();
    const comingSoon = await screen.findAllByTestId('app-coming-soon');
    expect(comingSoon[0]).toBeDisabled();
    expect(screen.queryByTestId('app-install')).not.toBeInTheDocument();
  });

  it('owner can install a free app', async () => {
    useApp.mockReturnValue(querySuccess(catalogApp()));
    renderAt('/apps/google-drive');
    fireEvent.click(await screen.findByTestId('app-install'));
    fireEvent.click(await screen.findByTestId('app-confirm-action'));
    await waitFor(() => {
      expect(installMutate).toHaveBeenCalledWith('google-drive');
    });
  });

  it('owner can uninstall', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          can_install: false,
          can_uninstall: true,
          installation_status: 'active',
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
        }),
      ),
    );
    renderAt('/apps/google-drive');
    fireEvent.click(await screen.findByTestId('app-uninstall'));
    fireEvent.click(await screen.findByTestId('app-confirm-action'));
    await waitFor(() => {
      expect(uninstallMutate).toHaveBeenCalledWith('google-drive');
    });
  });

  it('member cannot install', async () => {
    workspaceState.role = 'member';
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          can_install: false,
          can_uninstall: false,
          access: {
            status: 'entitled_not_installed',
            plan_id: 'plan-1',
            plan_code: 'free',
            plan_name: 'Free',
            current_period_start: null,
            current_period_end: null,
            commercially_entitled: true,
            can_purchase: false,
            can_renew: false,
            can_install: false,
            can_uninstall: false,
          },
        }),
      ),
    );
    renderAt('/apps/google-drive');
    expect(await screen.findByTestId('app-member-hint')).toBeInTheDocument();
    expect(screen.queryByTestId('app-install')).not.toBeInTheDocument();
  });

  it('one-time app shows Buy & Install with plan price', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'paid-demo',
          name: 'Paid Demo',
          billing_type: 'one_time',
          can_install: false,
          access_requirement: 'one_time',
          connector: null,
          plans: [
            {
              id: 'p',
              code: 'buy',
              name: 'Buy',
              description: null,
              billing_interval: 'none',
              price_amount: '299.00',
              currency: 'SAR',
              is_default: true,
              entitlements: {},
            },
          ],
          access: {
            status: 'not_entitled',
            plan_id: null,
            plan_code: null,
            plan_name: null,
            current_period_start: null,
            current_period_end: null,
            commercially_entitled: false,
            can_purchase: true,
            can_renew: false,
            can_install: false,
            can_uninstall: false,
          },
        }),
      ),
    );
    renderAt('/apps/paid-demo');
    expect(await screen.findByTestId('app-detail-sheet')).toBeInTheDocument();
    expect(screen.getByTestId('app-plan-buy')).toBeInTheDocument();
    expect(screen.getAllByLabelText('SAR 299.00').length).toBeGreaterThan(0);
    expect(screen.getAllByTestId('app-buy-buy').length).toBeGreaterThan(0);
    expect(screen.queryByText(/auto renew/i)).not.toBeInTheDocument();
  });

  it('subscription app shows plan cards and manual renewal copy', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'sub-demo',
          name: 'Sub Demo',
          billing_type: 'subscription',
          can_install: false,
          access_requirement: 'subscription',
          connector: null,
          plans: [
            {
              id: 's1',
              code: 'starter',
              name: 'Starter',
              description: null,
              billing_interval: 'monthly',
              price_amount: '49.00',
              currency: 'SAR',
              is_default: false,
              entitlements: { sessions: 1 },
            },
            {
              id: 's2',
              code: 'pro',
              name: 'Pro',
              description: null,
              billing_interval: 'monthly',
              price_amount: '149.00',
              currency: 'SAR',
              is_default: true,
              entitlements: { sessions: 3 },
            },
          ],
          access: {
            status: 'not_entitled',
            plan_id: null,
            plan_code: null,
            plan_name: null,
            current_period_start: null,
            current_period_end: null,
            commercially_entitled: false,
            can_purchase: true,
            can_renew: false,
            can_install: false,
            can_uninstall: false,
          },
        }),
      ),
    );
    renderAt('/apps/sub-demo');
    expect(await screen.findByTestId('app-plan-pro')).toBeInTheDocument();
    expect(screen.getByTestId('app-plan-starter')).toBeInTheDocument();
    expect(screen.getAllByText(i18n.t('apps.billing.manualRenewal')).length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText(/auto renew/i)).not.toBeInTheDocument();
  });

  it('uninstalled connector app with plans opens the plans tab', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'whatsapp',
          name: 'WhatsApp',
          billing_type: 'subscription',
          status: 'published',
          can_install: false,
          access_requirement: 'subscription',
          installation_status: null,
          plans: [
            {
              id: 'line',
              code: 'line',
              name: 'WhatsApp Line',
              description: null,
              billing_interval: 'monthly',
              price_amount: '79.00',
              currency: 'SAR',
              is_default: true,
              entitlements: { connections: 1 },
            },
          ],
          access: {
            status: 'not_entitled',
            plan_id: null,
            plan_code: null,
            plan_name: null,
            current_period_start: null,
            current_period_end: null,
            commercially_entitled: false,
            can_purchase: true,
            can_renew: false,
            can_install: false,
            can_uninstall: false,
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
        }),
      ),
    );
    renderAt('/apps/whatsapp');
    expect(await screen.findByTestId('app-detail-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('app-tab-plans')).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('app-plan-line')).toBeInTheDocument();
    expect(screen.getByTestId('app-tab-connections')).toHaveAttribute(
      'data-state',
      'inactive',
    );
  });

  it('installed connector app with plans opens the connections tab', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'whatsapp',
          name: 'WhatsApp',
          billing_type: 'subscription',
          status: 'published',
          can_install: false,
          can_uninstall: true,
          installation_status: 'active',
          access_requirement: 'subscription',
          plans: [
            {
              id: 'line',
              code: 'line',
              name: 'WhatsApp Line',
              description: null,
              billing_interval: 'monthly',
              price_amount: '79.00',
              currency: 'SAR',
              is_default: true,
              entitlements: { connections: 1 },
            },
          ],
          access: {
            status: 'active',
            plan_id: 'line',
            plan_code: 'line',
            plan_name: 'WhatsApp Line',
            current_period_start: '2026-08-01T00:00:00Z',
            current_period_end: '2026-09-01T00:00:00Z',
            commercially_entitled: true,
            can_purchase: true,
            can_renew: true,
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
        }),
      ),
    );
    renderAt('/apps/whatsapp');
    expect(await screen.findByTestId('app-detail-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('app-tab-connections')).toHaveAttribute(
      'data-state',
      'active',
    );
  });

  it('active subscription shows renew and period end', async () => {
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'sub-demo',
          billing_type: 'subscription',
          can_install: false,
          can_uninstall: true,
          installation_status: 'active',
          access_requirement: 'subscription',
          plans: [],
          access: {
            status: 'active',
            plan_id: 's2',
            plan_code: 'pro',
            plan_name: 'Pro',
            current_period_start: '2026-08-17T00:00:00Z',
            current_period_end: '2026-09-17T00:00:00Z',
            commercially_entitled: true,
            can_purchase: false,
            can_renew: true,
            can_install: false,
            can_uninstall: true,
          },
        }),
      ),
    );
    renderAt('/apps/sub-demo');
    expect(await screen.findByTestId('app-subscription-active')).toBeInTheDocument();
    expect(screen.getByTestId('app-renew')).toBeInTheDocument();
    expect(screen.queryByText(/auto renew/i)).not.toBeInTheDocument();
  });

  it('member cannot purchase', async () => {
    workspaceState.role = 'member';
    useApp.mockReturnValue(
      querySuccess(
        catalogApp({
          slug: 'paid-demo',
          billing_type: 'one_time',
          can_install: false,
          access_requirement: 'one_time',
          plans: [
            {
              id: 'p',
              code: 'buy',
              name: 'Buy',
              description: null,
              billing_interval: 'none',
              price_amount: '99.00',
              currency: 'SAR',
              is_default: true,
              entitlements: {},
            },
          ],
          access: {
            status: 'not_entitled',
            plan_id: null,
            plan_code: null,
            plan_name: null,
            current_period_start: null,
            current_period_end: null,
            commercially_entitled: false,
            can_purchase: false,
            can_renew: false,
            can_install: false,
            can_uninstall: false,
          },
        }),
      ),
    );
    renderAt('/apps/paid-demo');
    expect(await screen.findByTestId('app-member-hint')).toBeInTheDocument();
    expect(screen.queryByTestId('app-buy-buy')).not.toBeInTheDocument();
  });

  it('lists installed apps', async () => {
    useAppInstallations.mockReturnValue(
      querySuccess({
        items: [
          {
            id: 'inst-1',
            workspace_id: 'ws-a',
            app_id: 'app-1',
            status: 'active',
            installed_at: '2026-08-01T00:00:00Z',
            uninstalled_at: null,
            installed_by_user_id: 'u1',
            app: catalogApp({
              can_install: false,
              can_uninstall: true,
              installation_status: 'active',
            }),
          },
        ],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    );
    renderAt('/apps/installed');
    expect(await screen.findByTestId('installed-app-google-drive')).toBeInTheDocument();
    expect(screen.getByText(i18n.t('apps.connections.notConnected'))).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t('apps.connections.connectorAvailableSoon')),
    ).toBeInTheDocument();
  });

  it('scopes React Query keys by workspace', () => {
    expect(queryKeys.apps('ws-a')[1]).toBe('ws-a');
    expect(queryKeys.appInstallations('ws-b')[1]).toBe('ws-b');
    expect(queryKeys.app('ws-a', 'google-drive')).toEqual([
      'workspace',
      'ws-a',
      'apps',
      'detail',
      'google-drive',
    ]);
    expect(queryKeys.apps('ws-a')).not.toEqual(queryKeys.apps('ws-b'));
  });

  it('maps typed backend errors', () => {
    expect(errorMessageKey('app_billing_required')).toBe('errors.appBillingRequired');
    expect(errorMessageKey('app_not_available')).toBe('errors.appNotAvailable');
    expect(errorMessageKey('app_already_installed')).toBe('errors.appAlreadyInstalled');
    const err = new ApiError('x', { status: 402, code: 'app_billing_required' });
    expect(err.code).toBe('app_billing_required');
  });

  it('renders Arabic store chrome', async () => {
    await i18n.changeLanguage('ar');
    renderAt('/apps');
    expect(await screen.findByTestId('apps-page')).toBeInTheDocument();
    expect(screen.getByText(i18n.t('apps.title'))).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: i18n.t('apps.filters.all') })).toBeInTheDocument();
  });
});
