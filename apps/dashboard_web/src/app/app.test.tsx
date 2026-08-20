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
    expect(screen.getByTestId('admin-identity-card')).toHaveTextContent('admin@example.com');
    expect(screen.getByTestId('platform-role-badge')).toHaveTextContent(/مدير منصة|Platform Admin/);
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
        return json({
          items: [
            {
              id: 'admin-1',
              email: 'admin@example.com',
              status: 'active',
              platform_role: 'admin',
              created_at: '2026-01-01T00:00:00Z',
              workspace_memberships_count: 0,
            },
            {
              id: 'user-2',
              email: 'owner@example.com',
              status: 'active',
              platform_role: 'none',
              created_at: '2026-01-02T00:00:00Z',
              workspace_memberships_count: 1,
            },
          ],
          total: 2,
          limit: 25,
          offset: 0,
        });
      }
      return json({}, 404);
    });

    const user = userEvent.setup();
    render(<AppProviders />);
    await screen.findByTestId('overview-page');
    await user.click(screen.getByTestId('nav-users'));
    expect(await screen.findByTestId('users-page')).toBeInTheDocument();
    expect(screen.getByText('owner@example.com')).toBeInTheDocument();

    await user.click(screen.getByText('admin@example.com'));
    expect(await screen.findByTestId('user-detail-page')).toBeInTheDocument();
    expect(screen.getByTestId('user-self-protected')).toBeInTheDocument();
    expect(screen.queryByTestId('user-disable-button')).not.toBeInTheDocument();
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
});
