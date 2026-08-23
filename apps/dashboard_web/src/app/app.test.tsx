import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppProviders } from '@/app/providers';
import { THEME_STORAGE_KEY } from '@/lib/helpers';
import { __resetRefreshStateForTests } from '@/services/api/client';
import { clearAuthSession } from '@/services/auth/session';

const adminUser = {
  id: 'admin-1',
  email: 'admin@example.com',
  status: 'active',
  platform_role: 'admin',
  created_at: '2026-01-01T00:00:00Z',
  email_verified_at: '2026-01-01T00:00:00Z',
};

const normalUser = {
  ...adminUser,
  id: 'user-1',
  email: 'owner@example.com',
  platform_role: 'none',
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function empty(status: number) {
  return new Response(null, { status });
}

function installFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      return handler(url, init);
    }),
  );
}

describe('Platform Admin app', () => {
  beforeEach(() => {
    __resetRefreshStateForTests();
    clearAuthSession();
    window.history.pushState({}, '', '/');
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    __resetRefreshStateForTests();
    clearAuthSession();
  });

  it('redirects anonymous visitors to admin login', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({ code: 'unauthorized', message: 'no' }, 401);
      }
      return json({ code: 'unauthorized' }, 401);
    });

    render(<AppProviders />);

    expect(await screen.findByTestId('login-form')).toBeInTheDocument();
    expect(screen.getByText(/Platform Admin sign in/i)).toBeInTheDocument();
  });

  it('signs in a platform admin and renders Overview', async () => {
    installFetch(async (url, init) => {
      if (url.includes('/api/auth/refresh')) {
        return json({ code: 'unauthorized' }, 401);
      }
      if (url.includes('/api/auth/login') && init?.method === 'POST') {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/dashboard/summary')) {
        return json({
          workspaces: { total: 1, active: 1, disabled: 0 },
          users: { total: 1, active: 1, disabled: 0 },
          experts: { published: 0, draft: 0 },
          usage: {
            billed_tokens_24h: 0,
            billed_tokens_7d: 0,
            billed_tokens_30d: 0,
            active_workspaces_30d: 0,
            outstanding_credit_balance: 0,
          },
          billing: {
            active_subscriptions: 0,
            pending_purchases: 0,
            failed_purchases_30d: 0,
            paid_purchase_count_30d: 0,
            paid_purchase_volume_30d: '0',
          },
          apps: {
            published: 0,
            active_subscriptions: 0,
            active_licenses: 0,
            installations: 0,
          },
          gateway: null,
          recent_activity: [],
        });
      }
      return json({ code: 'not_found' }, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('login-form');

    await user.type(screen.getByLabelText(/email/i), 'admin@example.com');
    await user.type(screen.getByPlaceholderText(/your password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByTestId('overview-page')).toBeInTheDocument();
    expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
    expect(await screen.findByTestId('overview-billing-card')).toBeInTheDocument();
    expect(screen.getByTestId('admin-nav')).toBeInTheDocument();
  });

  it('denies authenticated non-admin users', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({ code: 'unauthorized' }, 401);
      }
      if (url.includes('/api/auth/login')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: normalUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json(
          { code: 'platform_admin_required', message: 'Platform admin role required.' },
          403,
        );
      }
      if (url.includes('/api/auth/logout')) {
        return empty(204);
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('login-form');
    await user.type(screen.getByLabelText(/email/i), 'owner@example.com');
    await user.type(screen.getByPlaceholderText(/your password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByTestId('platform-access-required')).toBeInTheDocument();
    expect(screen.queryByTestId('overview-page')).not.toBeInTheDocument();
  });

  it('bootstraps an existing admin session onto protected routes', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      return json({}, 404);
    });

    render(<AppProviders />);
    expect(await screen.findByTestId('overview-page')).toBeInTheDocument();
    expect(screen.getByTestId('admin-layout')).toBeInTheDocument();
  });

  it('logs out from the account menu', async () => {
    installFetch(async (url, init) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/auth/logout') && init?.method === 'POST') {
        return empty(204);
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');

    await user.click(screen.getAllByTestId('account-menu-trigger')[0]);
    await user.click(await screen.findByTestId('logout-menu-item'));
    await user.click(await screen.findByTestId('logout-confirm'));

    expect(await screen.findByTestId('login-form')).toBeInTheDocument();
  });

  it('renders Workspaces list from Platform Admin API', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/workspaces') && !url.includes('/members')) {
        return json({
          items: [
            {
              id: 'ws-1',
              name: 'Acme',
              slug: 'acme',
              kind: 'tenant',
              status: 'active',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
              members_count: 2,
              experts_count: 1,
              current_plan_code: 'free',
              current_plan_name: 'Free',
              subscription_status: 'active',
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    expect(screen.getByTestId('nav-workspaces')).toBeInTheDocument();

    await user.click(screen.getByTestId('nav-workspaces'));
    expect(await screen.findByTestId('workspaces-page')).toBeInTheDocument();
    expect(screen.getByTestId('workspaces-list')).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.queryByTestId('coming-soon-page')).not.toBeInTheDocument();
  });

  it('renders Users list and hides self-disable on detail', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/users/') && !url.includes('/disable')) {
        const id = url.split('/api/platform/users/')[1]?.split('?')[0];
        return json({
          id,
          email: id === 'admin-1' ? 'admin@example.com' : 'owner@example.com',
          status: 'active',
          platform_role: id === 'admin-1' ? 'admin' : 'none',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          email_verified_at: '2026-01-01T00:00:00Z',
          last_login_at: '2026-01-03T12:00:00Z',
          active_session_count: 1,
          memberships: [
            {
              membership_id: 'm1',
              workspace_id: 'ws-1',
              workspace_name: 'Acme',
              workspace_slug: 'acme',
              workspace_status: 'active',
              role_id: 'r1',
              role_name: 'Owner',
              is_owner_role: true,
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
        });
      }
      if (url.includes('/api/platform/users')) {
        const requestUrl = new URL(url);
        const items = [
          {
            id: 'admin-1',
            email: 'admin@example.com',
            status: 'active',
            platform_role: 'admin',
            created_at: '2026-01-01T00:00:00Z',
            email_verified_at: '2026-01-01T00:00:00Z',
            last_login_at: '2026-01-03T12:00:00Z',
            workspace_memberships_count: 0,
          },
          {
            id: 'user-2',
            email: 'owner@example.com',
            status: 'active',
            platform_role: 'none',
            created_at: '2026-01-02T00:00:00Z',
            email_verified_at: null,
            last_login_at: '2026-01-03T10:00:00Z',
            workspace_memberships_count: 1,
          },
        ];
        const status = requestUrl.searchParams.get('status');
        const role = requestUrl.searchParams.get('platform_role');
        const search = requestUrl.searchParams.get('search')?.toLowerCase();
        const filtered = items.filter((item) => {
          if (status && item.status !== status) return false;
          if (role && item.platform_role !== role) return false;
          if (search && !item.email.toLowerCase().includes(search)) return false;
          return true;
        });
        const limit = Number(requestUrl.searchParams.get('limit') ?? 25);
        const offset = Number(requestUrl.searchParams.get('offset') ?? 0);
        return json({
          items: filtered.slice(offset, offset + limit),
          total: filtered.length,
          limit,
          offset,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    await user.click(screen.getByTestId('nav-users'));
    expect(await screen.findByTestId('users-page')).toBeInTheDocument();
    expect(screen.getByTestId('user-inventory-summary')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('user-stat-total')).toHaveTextContent('2');
      expect(screen.getByTestId('user-stat-active')).toHaveTextContent('2');
      expect(screen.getByTestId('user-stat-disabled')).toHaveTextContent('0');
      expect(screen.getByTestId('user-stat-admins')).toHaveTextContent('1');
    });
    expect(screen.getByTestId('user-results-count')).toHaveTextContent('2 matching');
    expect(screen.getByTestId('users-list')).toHaveTextContent('Verified');
    expect(screen.getByTestId('users-list')).toHaveTextContent('Unverified');
    expect(screen.getByText('owner@example.com')).toBeInTheDocument();

    await user.click(screen.getByText('admin@example.com'));
    expect(await screen.findByTestId('user-detail-page')).toBeInTheDocument();
    expect(screen.getByTestId('user-resource-summary')).toBeInTheDocument();
    expect(screen.getByTestId('user-account-overview')).toBeInTheDocument();
    expect(screen.getByTestId('user-lifecycle-summary')).toBeInTheDocument();
    expect(screen.getByTestId('user-memberships-card')).toHaveTextContent('Acme');
    expect(screen.getByTestId('user-self-protected')).toBeInTheDocument();
    expect(screen.queryByTestId('user-disable-button')).not.toBeInTheDocument();
  });

  it('renders Plans list from Platform Admin API', async () => {
    const plans = Array.from({ length: 101 }, (_, index) => ({
      id: `plan-${index + 1}`,
      code: index === 0 ? 'free' : `plan-${index + 1}`,
      name: index === 0 ? 'Free' : `Plan ${index + 1}`,
      description: null,
      status: index === 100 ? 'archived' : 'active',
      price_amount: null,
      currency: 'SAR',
      is_bootstrap: index === 0,
      is_commercial: false,
      subscriber_count: index === 0 ? 3 : 1,
      entitlements: [
        { key: 'experts_limit', value: 3, value_type: 'integer' },
        { key: 'storage_bytes', value: 1073741824, value_type: 'integer' },
      ],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }));

    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/plans') && !url.includes('/plans/')) {
        const requestUrl = new URL(url);
        const limit = Number(requestUrl.searchParams.get('limit') ?? 25);
        const offset = Number(requestUrl.searchParams.get('offset') ?? 0);
        return json({
          items: plans.slice(offset, offset + limit),
          total: plans.length,
          limit,
          offset,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    await user.click(screen.getByTestId('nav-plans'));
    expect(await screen.findByTestId('plans-page')).toBeInTheDocument();
    expect(screen.getByTestId('plan-inventory-summary')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('plan-stat-total')).toHaveTextContent('101');
      expect(screen.getByTestId('plan-stat-active')).toHaveTextContent('100');
      expect(screen.getByTestId('plan-stat-archived')).toHaveTextContent('1');
      expect(screen.getByTestId('plan-stat-subscribers')).toHaveTextContent('103');
    });
    expect(screen.getByTestId('plan-results-count')).toHaveTextContent('101 matching');
    expect(screen.getByText('Showing the full plan catalog.')).toBeInTheDocument();
    expect(screen.getByTestId('plans-list')).toBeInTheDocument();
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByTestId('plan-bootstrap-badge')).toBeInTheDocument();
    expect(screen.queryByTestId('coming-soon-page')).not.toBeInTheDocument();
  });

  it('creates a plan from the enriched direct create route', async () => {
    window.history.pushState({}, '', '/plans/new');
    const entitlementCatalog = {
      items: [
        { key: 'ai_tokens_daily', value_type: 'integer', unit: 'tokens' },
        { key: 'ai_tokens_weekly', value_type: 'integer', unit: 'tokens' },
        { key: 'ai_tokens_monthly', value_type: 'integer', unit: 'tokens' },
        { key: 'experts_limit', value_type: 'integer', unit: 'experts' },
        { key: 'storage_bytes', value_type: 'integer', unit: 'bytes' },
        {
          key: 'api_requests_per_minute',
          value_type: 'integer',
          unit: 'requests_per_minute',
        },
      ],
    };
    const createdPlan = {
      id: 'plan-created',
      code: 'team',
      name: 'Team',
      description: 'For growing Workspace teams.',
      status: 'active',
      price_amount: '149.25',
      currency: 'SAR',
      is_bootstrap: false,
      is_commercial: true,
      subscriber_count: 0,
      entitlements: [
        { key: 'ai_tokens_daily', value: 1000, value_type: 'integer' },
        { key: 'ai_tokens_weekly', value: 5000, value_type: 'integer' },
        { key: 'ai_tokens_monthly', value: 20000, value_type: 'integer' },
        { key: 'experts_limit', value: 10, value_type: 'integer' },
        { key: 'storage_bytes', value: 2147483648, value_type: 'integer' },
        { key: 'api_requests_per_minute', value: 120, value_type: 'integer' },
      ],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    const createRequests: unknown[] = [];

    installFetch(async (url, init) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.endsWith('/api/platform/entitlement-catalog')) {
        return json(entitlementCatalog);
      }
      if (url.endsWith('/api/platform/plans') && init?.method === 'POST') {
        createRequests.push(JSON.parse(String(init.body)));
        return json(createdPlan, 201);
      }
      if (url.endsWith('/api/platform/plans/plan-created')) {
        return json(createdPlan);
      }
      if (url.includes('/api/auth/logout') && init?.method === 'POST') {
        return empty(204);
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);

    expect(await screen.findByTestId('plan-create-page')).toBeInTheDocument();
    expect(screen.getByText('Plan configuration')).toBeInTheDocument();
    expect(screen.getByTestId('plan-create-summary')).toBeInTheDocument();
    expect(screen.getByTestId('plan-entitlements')).toBeInTheDocument();

    await user.type(screen.getByTestId('plan-code-input'), ' team ');
    await user.type(screen.getByTestId('plan-name-input'), ' Team ');
    await user.type(
      screen.getByTestId('plan-description-input'),
      ' For growing Workspace teams. ',
    );
    await user.type(screen.getByTestId('plan-price-input'), '149.25');
    await user.type(screen.getByTestId('plan-entitlements-ai_tokens_daily'), '1000');
    await user.type(screen.getByTestId('plan-entitlements-ai_tokens_weekly'), '5000');
    await user.type(screen.getByTestId('plan-entitlements-ai_tokens_monthly'), '20000');
    await user.type(screen.getByTestId('plan-entitlements-experts_limit'), '10');
    await user.type(screen.getByTestId('plan-entitlements-storage_bytes'), '2');
    await user.type(screen.getByTestId('plan-entitlements-api_requests_per_minute'), '120');
    await user.click(screen.getByTestId('plan-create-submit'));

    await waitFor(() => {
      expect(createRequests).toEqual([
        {
          code: 'team',
          name: 'Team',
          description: 'For growing Workspace teams.',
          price_amount: '149.25',
          currency: 'SAR',
          entitlements: [
            { key: 'ai_tokens_daily', value: 1000 },
            { key: 'ai_tokens_weekly', value: 5000 },
            { key: 'ai_tokens_monthly', value: 20000 },
            { key: 'experts_limit', value: 10 },
            { key: 'storage_bytes', value: 2147483648 },
            { key: 'api_requests_per_minute', value: 120 },
          ],
        },
      ]);
      expect(window.location.pathname).toBe('/plans/plan-created');
    });

    // The application QueryClient is shared across AppProviders instances, so end this
    // direct-route flow through the real logout path to preserve test isolation.
    await user.click(screen.getAllByTestId('account-menu-trigger')[0]);
    await user.click(await screen.findByTestId('logout-menu-item'));
    await user.click(await screen.findByTestId('logout-confirm'));
    expect(await screen.findByTestId('login-form')).toBeInTheDocument();
  });

  it('keeps plan details editable through catalog recovery and safeguards entitlement updates', async () => {
    window.history.pushState({}, '', '/plans/plan-safety');
    const entitlementCatalog = {
      items: [
        { key: 'ai_tokens_daily', value_type: 'integer', unit: 'tokens' },
        { key: 'ai_tokens_weekly', value_type: 'integer', unit: 'tokens' },
        { key: 'ai_tokens_monthly', value_type: 'integer', unit: 'tokens' },
        { key: 'experts_limit', value_type: 'integer', unit: 'experts' },
        { key: 'storage_bytes', value_type: 'integer', unit: 'bytes' },
        {
          key: 'api_requests_per_minute',
          value_type: 'integer',
          unit: 'requests_per_minute',
        },
      ],
    };
    let catalogAvailable = false;
    let serverPlan = {
      id: 'plan-safety',
      code: 'pro',
      name: 'Pro',
      description: 'Commercial plan for growing teams.',
      status: 'active',
      price_amount: '99.25',
      currency: 'SAR',
      is_bootstrap: false,
      is_commercial: true,
      subscriber_count: 4,
      entitlements: [
        { key: 'ai_tokens_daily', value: 10000, value_type: 'integer' },
        { key: 'ai_tokens_weekly', value: 50000, value_type: 'integer' },
        { key: 'ai_tokens_monthly', value: 200000, value_type: 'integer' },
        { key: 'experts_limit', value: 20, value_type: 'integer' },
        { key: 'storage_bytes', value: 1073741824, value_type: 'integer' },
        { key: 'api_requests_per_minute', value: 120, value_type: 'integer' },
      ],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    };
    type PlanUpdateRequest = {
      name?: string;
      description?: string | null;
      price_amount?: string | null;
      clear_price?: boolean;
      currency?: string;
      entitlements?: Array<{ key: string; value: number }>;
      reason?: string | null;
    };
    const updateRequests: PlanUpdateRequest[] = [];

    installFetch(async (url, init) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.endsWith('/api/platform/entitlement-catalog')) {
        return catalogAvailable
          ? json(entitlementCatalog)
          : json({ code: 'service_unavailable', message: 'Catalog unavailable' }, 503);
      }
      if (url.endsWith('/api/platform/plans/plan-safety') && init?.method === 'PATCH') {
        const request = JSON.parse(String(init.body)) as PlanUpdateRequest;
        updateRequests.push(request);
        serverPlan = {
          ...serverPlan,
          name: request.name ?? serverPlan.name,
          description:
            request.description === undefined ? serverPlan.description : request.description ?? '',
          price_amount: request.clear_price
            ? ''
            : request.price_amount === undefined
              ? serverPlan.price_amount
              : request.price_amount ?? '',
          entitlements: request.entitlements
            ? request.entitlements.map((item) => ({ ...item, value_type: 'integer' }))
            : serverPlan.entitlements,
          updated_at: '2026-01-03T00:00:00Z',
        };
        return json(serverPlan);
      }
      if (url.endsWith('/api/platform/plans/plan-safety')) {
        return json(serverPlan);
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<AppProviders />);

    expect(await screen.findByTestId('plan-detail-page')).toBeInTheDocument();
    expect(
      await screen.findByTestId('plan-detail-catalog-error', {}, { timeout: 3000 }),
    ).toHaveTextContent('Entitlement catalog could not be loaded');
    expect(screen.getByTestId('plan-resource-summary')).toHaveTextContent('4');
    expect(screen.getByTestId('plan-entitlements-readonly')).toHaveTextContent('20');
    expect(screen.getByTestId('plan-deactivate-button')).toBeEnabled();
    expect(screen.getByTestId('plan-name-input')).toHaveValue('Pro');
    expect(screen.getByTestId('plan-save-button')).toBeEnabled();

    await user.clear(screen.getByTestId('plan-name-input'));
    await user.type(screen.getByTestId('plan-name-input'), 'Pro Plus');
    await user.click(screen.getByTestId('plan-save-button'));

    await waitFor(() => {
      expect(updateRequests).toEqual([
        {
          name: 'Pro Plus',
          description: 'Commercial plan for growing teams.',
          price_amount: '99.25',
          clear_price: false,
          currency: 'SAR',
          reason: null,
        },
      ]);
    });

    catalogAvailable = true;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByTestId('plan-entitlements')).toBeInTheDocument();
    expect(screen.getByTestId('plan-entitlements-experts_limit')).toHaveValue(20);
    expect(screen.getByTestId('plan-edit-reason')).toBeInTheDocument();

    await user.clear(screen.getByTestId('plan-entitlements-experts_limit'));
    await user.type(screen.getByTestId('plan-entitlements-experts_limit'), '25');
    await user.click(screen.getByTestId('plan-save-button'));
    expect(
      await screen.findByText(
        'A reason is required when changing entitlements on an in-use plan.',
      ),
    ).toBeInTheDocument();
    expect(updateRequests).toHaveLength(1);

    await user.type(screen.getByTestId('plan-edit-reason'), 'Expand expert capacity');
    await user.click(screen.getByTestId('plan-save-button'));

    await waitFor(() => {
      expect(updateRequests).toEqual([
        {
          name: 'Pro Plus',
          description: 'Commercial plan for growing teams.',
          price_amount: '99.25',
          clear_price: false,
          currency: 'SAR',
          reason: null,
        },
        {
          name: 'Pro Plus',
          description: 'Commercial plan for growing teams.',
          price_amount: '99.25',
          clear_price: false,
          currency: 'SAR',
          entitlements: [
            { key: 'ai_tokens_daily', value: 10000 },
            { key: 'ai_tokens_weekly', value: 50000 },
            { key: 'ai_tokens_monthly', value: 200000 },
            { key: 'experts_limit', value: 25 },
            { key: 'storage_bytes', value: 1073741824 },
            { key: 'api_requests_per_minute', value: 120 },
          ],
          reason: 'Expand expert capacity',
        },
      ]);
      expect(screen.getByTestId('plan-edit-reason')).toHaveValue('');
    });

    serverPlan = {
      ...serverPlan,
      name: 'Server-synced Pro',
      description: 'Updated outside this session.',
      updated_at: '2026-01-04T00:00:00Z',
    };
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => {
      expect(screen.getByTestId('plan-name-input')).toHaveValue('Server-synced Pro');
      expect(screen.getByTestId('plan-description-input')).toHaveValue(
        'Updated outside this session.',
      );
    });
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('renders Credits page and loads balance for selected workspace', async () => {
    const grantRequests: Array<{ amount: number; reason: string; request_id: string }> = [];
    const consumeEntry = {
      id: 'credit-consume-1',
      entry_type: 'consume',
      amount: 75,
      remaining_amount: null,
      request_id: 'usage:request-1',
      source_type: 'ai_usage',
      source_id: 'usage-1',
      reason: 'AI token usage',
      created_at: '2026-01-02T12:00:00Z',
    };
    const firstPageWorkspaces = Array.from({ length: 25 }, (_, index) => ({
      id: index === 0 ? 'ws-1' : `ws-${index + 1}`,
      name: index === 0 ? 'Acme' : `Tenant ${index + 1}`,
      slug: index === 0 ? 'acme' : `tenant-${index + 1}`,
      kind: 'tenant',
      status: 'active',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      members_count: 2,
      experts_count: 1,
      current_plan_code: 'free',
      current_plan_name: 'Free',
      subscription_status: 'active',
    }));

    installFetch(async (url, init) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/workspaces') && url.includes('credits/history')) {
        return json({ items: [consumeEntry], total: 1, limit: 20, offset: 0 });
      }
      if (url.endsWith('/api/platform/workspaces/ws-1/credits/grant') && init?.method === 'POST') {
        const grantRequest = JSON.parse(String(init.body)) as {
          amount: number;
          reason: string;
          request_id: string;
        };
        grantRequests.push(grantRequest);
        return json({
          workspace_id: 'ws-1',
          balance: 1750,
          entry: {
            id: 'credit-grant-1',
            entry_type: 'grant',
            amount: 250,
            remaining_amount: 250,
            request_id: grantRequest.request_id,
            source_type: 'platform_admin',
            source_id: 'admin-1',
            reason: 'Service recovery adjustment',
            created_at: '2026-01-03T12:00:00Z',
          },
          idempotent_replay: false,
        });
      }
      if (url.includes('/api/platform/workspaces/') && url.includes('/credits')) {
        return json({
          workspace_id: 'ws-1',
          balance: 1500,
          recent: [consumeEntry],
        });
      }
      if (url.includes('/api/platform/workspaces')) {
        const offset = Number(new URL(url).searchParams.get('offset') ?? 0);
        return json({
          items:
            offset === 25
              ? [
                  {
                    ...firstPageWorkspaces[0],
                    id: 'ws-26',
                    name: 'Beta',
                    slug: 'beta',
                  },
                ]
              : firstPageWorkspaces,
          total: 26,
          limit: 25,
          offset,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    await user.click(screen.getByTestId('nav-credits'));
    expect(await screen.findByTestId('credits-page')).toBeInTheDocument();
    expect(await screen.findByTestId('credits-workspace-list')).toBeInTheDocument();
    await user.selectOptions(screen.getByTestId('credits-workspaces-status'), 'active');
    await waitFor(() => {
      expect(screen.getByTestId('credits-workspace-count')).toHaveTextContent('26 matching');
    });
    expect(screen.getByText('Results reflect your search and status filters.')).toBeInTheDocument();

    await user.click(screen.getByTestId('credits-workspaces-pagination-next'));
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    await user.click(screen.getByTestId('credits-workspaces-pagination-prev'));
    expect(await screen.findByText('Acme')).toBeInTheDocument();

    await user.click(screen.getByText('Acme'));
    expect(await screen.findByTestId('credits-balance')).toHaveTextContent(/1[,.]?500|1500/);
    const accountSummary = screen.getByTestId('credits-account-summary');
    expect(accountSummary).toHaveTextContent('Credit balance');
    expect(accountSummary).toHaveTextContent('Ledger entries');
    expect(accountSummary).toHaveTextContent('Latest movement');
    expect(accountSummary).toHaveTextContent('−75');
    expect(accountSummary).toHaveTextContent('Current plan');
    expect(accountSummary).toHaveTextContent('Free');

    const ledgerRow = await screen.findByTestId('credits-history-row');
    expect(ledgerRow).toHaveTextContent('Consumed');
    expect(screen.getByTestId('credits-entry-amount')).toHaveTextContent('−75');
    expect(ledgerRow).toHaveTextContent('AI token usage');

    await user.click(screen.getByTestId('credits-grant-button'));
    const grantDialog = await screen.findByTestId('grant-credits-dialog');
    expect(grantDialog).toHaveTextContent('Acme');
    expect(grantDialog).toHaveTextContent(/Current balance: 1[,.]?500 credits/);
    await user.type(screen.getByTestId('grant-credits-amount'), '250');
    await user.type(screen.getByTestId('grant-credits-reason'), 'Service recovery adjustment');
    await user.click(screen.getByTestId('grant-credits-continue'));

    const grantSummary = screen.getByTestId('grant-credits-summary');
    expect(grantSummary).toHaveTextContent('+250');
    expect(grantSummary).toHaveTextContent(/1[,.]?500|1500/);
    expect(grantSummary).toHaveTextContent(/1[,.]?750|1750/);
    expect(grantSummary).toHaveTextContent('Service recovery adjustment');
    expect(screen.getByTestId('grant-credits-confirm')).toBeInTheDocument();

    await user.click(screen.getByTestId('grant-credits-back'));
    expect(screen.queryByTestId('grant-credits-summary')).not.toBeInTheDocument();
    expect(screen.getByTestId('grant-credits-amount')).toHaveValue(250);
    expect(screen.getByTestId('grant-credits-reason')).toHaveValue(
      'Service recovery adjustment',
    );
    expect(screen.queryByTestId('grant-credits-confirm')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('grant-credits-continue'));
    await user.click(screen.getByTestId('grant-credits-confirm'));
    await waitFor(() => {
      expect(grantRequests[0]).toMatchObject({
        amount: 250,
        reason: 'Service recovery adjustment',
      });
    });
    expect(grantRequests[0]?.request_id).toMatch(/^platform-credit-grant:/);
    expect(screen.queryByTestId('grant-credits-dialog')).not.toBeInTheDocument();
  });

  it('opens a Workspace credit account directly with context, summary, and signed ledger', async () => {
    window.history.pushState({}, '', '/credits/ws-direct');
    const consumeEntry = {
      id: 'credit-direct-consume',
      entry_type: 'consume',
      amount: 75,
      remaining_amount: null,
      request_id: 'usage:direct-request',
      source_type: 'ai_usage',
      source_id: 'usage-direct',
      reason: 'Direct AI usage',
      created_at: '2026-01-02T12:00:00Z',
    };

    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/workspaces/ws-direct/credits/history')) {
        return json({ items: [consumeEntry], total: 1, limit: 20, offset: 0 });
      }
      if (url.endsWith('/api/platform/workspaces/ws-direct/credits')) {
        return json({
          workspace_id: 'ws-direct',
          balance: 1500,
          recent: [consumeEntry],
        });
      }
      if (url.endsWith('/api/platform/workspaces/ws-direct')) {
        return json({
          id: 'ws-direct',
          name: 'Direct Acme',
          slug: 'direct-acme',
          kind: 'tenant',
          status: 'active',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          members_count: 4,
          owners: [],
          subscription: {
            subscription_id: 'sub-direct',
            status: 'active',
            plan_id: 'plan-pro',
            plan_code: 'pro',
            plan_name: 'Pro',
            starts_at: '2026-01-01T00:00:00Z',
            current_period_start: '2026-01-01T00:00:00Z',
            current_period_end: '2026-02-01T00:00:00Z',
            ends_at: null,
          },
          resources: {
            members_count: 4,
            experts_count: 2,
            api_keys_count: 1,
            app_installations_count: 1,
            storage_used_bytes: 0,
            storage_limit_bytes: 10737418240,
          },
        });
      }
      return json({}, 404);
    });

    render(<AppProviders />);

    const detailPage = await screen.findByTestId('credit-detail-page');
    expect(detailPage).toHaveTextContent('Direct Acme');
    expect(detailPage).toHaveTextContent('direct-acme');
    expect(detailPage).toHaveTextContent('Active');
    expect(detailPage).toHaveTextContent('Tenant');

    const summary = screen.getByTestId('credit-detail-summary');
    expect(summary).toHaveTextContent('Credit balance');
    expect(summary).toHaveTextContent(/1[,.]?500|1500/);
    expect(summary).toHaveTextContent('Ledger entries');
    expect(summary).toHaveTextContent('Latest movement');
    expect(summary).toHaveTextContent('−75');
    expect(summary).toHaveTextContent('Current plan');
    expect(summary).toHaveTextContent('Pro');

    const ledgerRow = await screen.findByTestId('credits-history-row');
    expect(ledgerRow).toHaveTextContent('Consumed');
    expect(ledgerRow).toHaveTextContent('Direct AI usage');
    expect(screen.getByTestId('credits-entry-amount')).toHaveTextContent('−75');
    expect(screen.getByTestId('credit-detail-grant')).toBeEnabled();
    expect(screen.getByRole('link', { name: 'Open Workspace detail' })).toHaveAttribute(
      'href',
      '/workspaces/ws-direct',
    );
  });

  it('blocks credit grants until the selected balance is verified', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/credits/history')) {
        return json({ items: [], total: 0, limit: 20, offset: 0 });
      }
      if (url.endsWith('/api/platform/workspaces/ws-balance-error/credits')) {
        return json({ code: 'service_unavailable', message: 'Balance service unavailable' }, 503);
      }
      if (url.includes('/api/platform/workspaces')) {
        return json({
          items: [
            {
              id: 'ws-balance-error',
              name: 'Balance Error Workspace',
              slug: 'balance-error',
              kind: 'tenant',
              status: 'active',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
              members_count: 2,
              experts_count: 1,
              current_plan_code: 'free',
              current_plan_name: 'Free',
              subscription_status: 'active',
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    await user.click(screen.getByTestId('nav-credits'));
    await user.type(screen.getByTestId('credits-workspaces-search'), 'balance error');
    await user.click(await screen.findByText('Balance Error Workspace'));

    expect(
      await screen.findByTestId('credits-balance-error', {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('credits-grant-button')).toBeDisabled();
    expect(screen.queryByTestId('grant-credits-dialog')).not.toBeInTheDocument();
  });

  it('shows billing section on workspace detail', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/members')) {
        return json({ items: [], total: 0, limit: 50, offset: 0 });
      }
      if (url.includes('/subscription') && !url.includes('/subscriptions')) {
        return json({
          subscription_id: 'sub-1',
          status: 'active',
          plan_id: 'plan-1',
          plan_code: 'free',
          plan_name: 'Free',
          plan_status: 'active',
          starts_at: '2026-01-01T00:00:00Z',
          current_period_start: '2026-01-01T00:00:00Z',
          current_period_end: '2026-02-01T00:00:00Z',
          ends_at: null,
          source: 'bootstrap',
          created_at: '2026-01-01T00:00:00Z',
        });
      }
      if (url.includes('/entitlements')) {
        return json({
          workspace_id: 'ws-1',
          subscription_id: 'sub-1',
          plan_id: 'plan-1',
          plan_code: 'free',
          plan_name: 'Free',
          plan_status: 'active',
          items: [{ key: 'experts_limit', value: 3, value_type: 'integer' }],
        });
      }
      if (url.includes('/usage/summary')) {
        return json({
          workspace_id: 'ws-1',
          workspace_name: 'Acme',
          workspace_slug: 'acme',
          workspace_status: 'active',
          workspace_kind: 'tenant',
          from_day: '2026-01-01',
          to_day: '2026-01-30',
          total_billed_tokens: 1000,
          families: [],
          sources: [],
        });
      }
      if (url.includes('/usage/trend')) {
        return json({
          workspace_id: 'ws-1',
          from_day: '2026-01-01',
          to_day: '2026-01-30',
          points: [{ date: '2026-01-01', billed_tokens: 1000, active_workspaces: 1 }],
        });
      }
      if (url.includes('/usage')) {
        return json({
          ai_tokens_daily: { limit: 1000, used: 10, reserved: 0, remaining: 990 },
          ai_tokens_weekly: { limit: 5000, used: 10, reserved: 0, remaining: 4990 },
          ai_tokens_monthly: { limit: 20000, used: 10, reserved: 0, remaining: 19990 },
          experts: { limit: 3, used: 1, reserved: 0, remaining: 2 },
          storage_bytes: { limit: 1073741824, used: 0, reserved: 0, remaining: 1073741824 },
          credit_balance: 100,
        });
      }
      if (url.includes('/credits')) {
        return json({ workspace_id: 'ws-1', balance: 100, recent: [] });
      }
      if (url.includes('/api/platform/workspaces/') && url.endsWith('/apps')) {
        return json({ items: [] });
      }
      if (url.includes('/api/platform/workspaces/') && !url.includes('/workspaces?')) {
        return json({
          id: 'ws-1',
          name: 'Acme',
          slug: 'acme',
          kind: 'tenant',
          status: 'active',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          members_count: 1,
          owners: [],
          subscription: {
            subscription_id: 'sub-1',
            status: 'active',
            plan_id: 'plan-1',
            plan_code: 'free',
            plan_name: 'Free',
            starts_at: '2026-01-01T00:00:00Z',
            current_period_start: '2026-01-01T00:00:00Z',
            current_period_end: '2026-02-01T00:00:00Z',
            ends_at: null,
          },
          resources: {
            members_count: 1,
            experts_count: 0,
            api_keys_count: 0,
            app_installations_count: 0,
            storage_used_bytes: 0,
            storage_limit_bytes: 1073741824,
          },
        });
      }
      if (url.includes('/api/platform/workspaces')) {
        return json({
          items: [
            {
              id: 'ws-1',
              name: 'Acme',
              slug: 'acme',
              kind: 'tenant',
              status: 'active',
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
              members_count: 1,
              experts_count: 0,
              current_plan_code: 'free',
              current_plan_name: 'Free',
              subscription_status: 'active',
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    await user.click(screen.getByTestId('nav-workspaces'));
    await screen.findByTestId('workspaces-page');
    await user.click(screen.getByText('Acme'));
    expect(await screen.findByTestId('workspace-detail-page')).toBeInTheDocument();
    expect(await screen.findByTestId('workspace-billing-section')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-change-plan-button')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-grant-credits-button')).toBeInTheDocument();
    expect(await screen.findByTestId('workspace-entitlements-card')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-entitlements-plan')).toHaveTextContent('Free');
    expect(
      screen
        .getByTestId('workspace-entitlements-list')
        .querySelector('[data-entitlement-key="experts_limit"]'),
    ).toBeInTheDocument();
  });

  it('opens mobile navigation', async () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query.includes('max-width'),
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }),
    });
    Object.defineProperty(window, 'innerWidth', { writable: true, value: 500 });

    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    expect(await screen.findByTestId('admin-mobile-header')).toBeInTheDocument();
    await user.click(screen.getByTestId('mobile-nav-trigger'));
    expect(await screen.findByTestId('admin-nav')).toBeInTheDocument();
  });

  it('switches locale to Arabic and sets RTL', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({ code: 'unauthorized' }, 401);
      }
      return json({ code: 'unauthorized' }, 401);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('login-form');
    await user.click(screen.getByTestId('auth-language-ar'));
    await waitFor(() => {
      expect(document.documentElement.lang).toBe('ar');
      expect(document.documentElement.dir).toBe('rtl');
    });
    expect(screen.getByText(/دخول إدارة المنصة/)).toBeInTheDocument();
  });

  it('renders App Store list from Platform Admin API', async () => {
    window.history.pushState({}, '', '/app-store');
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/app-categories')) {
        return json({
          items: [
            {
              id: 'cat-1',
              slug: 'productivity',
              name_key: 'apps.categories.productivity',
              description_key: null,
              icon: null,
              sort_order: 1,
              is_active: true,
            },
          ],
        });
      }
      if (new URL(url, 'http://localhost').pathname === '/api/platform/apps') {
        return json({
          items: [
            {
              id: 'app-1',
              slug: 'whatsapp',
              name: 'WhatsApp',
              short_description: 'WhatsApp connector',
              category_slug: 'communication',
              category_name_key: 'apps.categories.communication',
              billing_type: 'subscription',
              status: 'published',
              icon_url: null,
              connector_key: 'openwa',
              connector_kind: 'connector',
              plans_count: 2,
              installations_count: 5,
              active_entitlements_count: 3,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-02T00:00:00Z',
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        });
      }
      return json({}, 404);
    });

    render(<AppProviders />);
    expect(await screen.findByTestId('app-store-page')).toBeInTheDocument();
    expect(await screen.findByText('WhatsApp')).toBeInTheDocument();
    expect(screen.queryByTestId('coming-soon-page')).not.toBeInTheDocument();
  });

  it('toggles dark theme from login chrome', async () => {
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({ code: 'unauthorized' }, 401);
      }
      return json({ code: 'unauthorized' }, 401);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('login-form');
    const toggle = screen.getByTestId('auth-theme-toggle');
    await user.click(toggle);
    await waitFor(() => {
      const stored = localStorage.getItem(THEME_STORAGE_KEY);
      expect(stored === 'dark' || stored === 'system' || stored === 'light').toBe(true);
    });
  });

  it('renders Usage analytics page from Platform Admin API', async () => {
    window.history.pushState({}, '', '/usage');
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/usage/summary')) {
        return json({
          from_day: '2026-01-01',
          to_day: '2026-01-30',
          total_billed_tokens: 42000,
          active_workspaces: 2,
          average_daily_billed_tokens: 1400,
          peak_day: { day: '2026-01-15', billed_tokens: 5000 },
          families: [{ family: 'chat', billed_tokens: 42000, percentage: 100 }],
          sources: [
            { source: 'api', billed_tokens: 30000, percentage: 71.43 },
            { source: 'interactive', billed_tokens: 12000, percentage: 28.57 },
          ],
        });
      }
      if (url.includes('/api/platform/usage/trend')) {
        return json({
          from_day: '2026-01-01',
          to_day: '2026-01-30',
          points: [{ date: '2026-01-15', billed_tokens: 5000, active_workspaces: 2 }],
        });
      }
      if (url.includes('/api/platform/usage/workspaces')) {
        return json({
          items: [
            {
              workspace_id: 'ws-1',
              workspace_name: 'Acme',
              workspace_slug: 'acme',
              workspace_status: 'active',
              billed_tokens: 42000,
              percentage_of_platform_usage: 100,
              active_days: 10,
              current_plan_code: 'pro',
              current_plan_name: 'Pro',
            },
          ],
          total: 1,
          limit: 10,
          offset: 0,
          from_day: '2026-01-01',
          to_day: '2026-01-30',
          platform_total_billed_tokens: 42000,
        });
      }
      return json({}, 404);
    });

    render(<AppProviders />);
    expect(await screen.findByTestId('usage-page')).toBeInTheDocument();
    expect(await screen.findByTestId('usage-preset-30')).toBeInTheDocument();
    expect(await screen.findByText('Acme')).toBeInTheDocument();
  });

  it('renders Audit Logs page from Platform Admin API', async () => {
    window.history.pushState({}, '', '/audit-logs');
    installFetch(async (url) => {
      if (url.includes('/api/auth/refresh')) {
        return json({
          access_token: 'access',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: adminUser,
        });
      }
      if (url.includes('/api/platform/me')) {
        return json({
          user: adminUser,
          platform_role: 'admin',
          authorized: true,
        });
      }
      if (url.includes('/api/platform/audit-logs')) {
        return json({
          items: [
            {
              id: 'audit-1',
              created_at: '2026-01-15T12:00:00Z',
              actor: { user_id: 'admin-1', api_key_id: null, email: 'admin@example.com' },
              workspace: null,
              action: 'payment_gateway.update',
              resource: { entity_type: 'payment_gateway', entity_id: 'gw-1' },
              request_id: 'req-1',
              summary: 'Gateway updated',
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        });
      }
      return json({}, 404);
    });

    render(<AppProviders />);
    expect(await screen.findByTestId('audit-logs-page')).toBeInTheDocument();
    expect(await screen.findByText('admin@example.com')).toBeInTheDocument();
    expect(await screen.findByText('payment_gateway.update')).toBeInTheDocument();
  });
});
