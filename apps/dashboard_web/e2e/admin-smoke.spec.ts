import { expect, test, type Route } from '@playwright/test';

const adminUser = {
  id: 'admin-1',
  email: 'admin@example.com',
  status: 'active',
  platform_role: 'admin',
  created_at: '2026-01-01T00:00:00Z',
  email_verified_at: '2026-01-01T00:00:00Z',
};

const workspaceUser = {
  ...adminUser,
  id: 'user-1',
  email: 'owner@example.com',
  platform_role: 'none',
};

const fixtureWorkspace = {
  id: 'ws-fixture-1',
  name: 'Fixture Acme',
  slug: 'fixture-acme',
  kind: 'tenant',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  created_by: 'user-1',
  members_count: 1,
  experts_count: 0,
  current_plan_code: 'free',
  current_plan_name: 'Free',
  subscription_status: 'active',
  owners: [
    {
      user_id: 'user-1',
      email: 'owner@example.com',
      status: 'active',
      membership_id: 'm1',
      role_id: 'r1',
      role_name: 'Owner',
    },
  ],
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
    storage_limit_bytes: 10737418240,
  },
};

const systemWorkspace = {
  ...fixtureWorkspace,
  id: 'ws-system-1',
  name: 'Platform Knowledge',
  slug: 'platform-knowledge',
  kind: 'system',
  members_count: 0,
  owners: [],
  subscription: null,
};

async function fulfillJson(route: Route, body: unknown, status = 200) {
  const origin = route.request().headers()['origin'] || '*';
  const cors = {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Methods': '*',
  };
  if (route.request().method() === 'OPTIONS') {
    await route.fulfill({ status: 204, headers: cors });
    return;
  }
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: cors,
    body: JSON.stringify(body),
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('geem-admin-locale', 'en');
    localStorage.setItem('geem-admin-theme', 'light');
  });
});

test('anonymous visitor is sent to admin login', async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    await fulfillJson(route, { code: 'unauthorized' }, 401);
  });
  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
});

test('admin workspaces disable/enable smoke + system protected', async ({ page }) => {
  let loggedIn = false;
  let workspaceStatus = 'active';

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path.endsWith('/auth/refresh') && method === 'POST') {
      if (!loggedIn) return fulfillJson(route, { code: 'unauthorized' }, 401);
      return fulfillJson(route, {
        access_token: 'e2e-access',
        token_type: 'bearer',
        user: adminUser,
      });
    }
    if (path.endsWith('/auth/login') && method === 'POST') {
      loggedIn = true;
      return fulfillJson(route, {
        access_token: 'e2e-access',
        token_type: 'bearer',
        expires_at: '2099-01-01T00:00:00Z',
        user: adminUser,
      });
    }
    if (path.endsWith('/platform/me') && method === 'GET') {
      if (!loggedIn) return fulfillJson(route, { code: 'unauthorized' }, 401);
      return fulfillJson(route, {
        user: adminUser,
        platform_role: 'admin',
        authorized: true,
      });
    }
    if (path.endsWith('/auth/logout') && method === 'POST') {
      loggedIn = false;
      return route.fulfill({ status: 204, body: '' });
    }

    if (path.endsWith('/platform/workspaces') && method === 'GET') {
      const kind = url.searchParams.get('kind');
      if (kind === 'system') {
        return fulfillJson(route, {
          items: [systemWorkspace],
          total: 1,
          limit: 25,
          offset: 0,
        });
      }
      return fulfillJson(route, {
        items: [{ ...fixtureWorkspace, status: workspaceStatus }],
        total: 1,
        limit: 25,
        offset: 0,
      });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/disable') && method === 'POST') {
      const id = path.split('/')[4];
      if (id === systemWorkspace.id) {
        return fulfillJson(
          route,
          { code: 'system_workspace_protected', message: 'System workspaces cannot be disabled.' },
          409,
        );
      }
      workspaceStatus = 'suspended';
      return fulfillJson(route, { ...fixtureWorkspace, status: 'suspended' });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/enable') && method === 'POST') {
      workspaceStatus = 'active';
      return fulfillJson(route, { ...fixtureWorkspace, status: 'active' });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/members') && method === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            membership_id: 'm1',
            user_id: 'user-1',
            email: 'owner@example.com',
            user_status: 'active',
            role_id: 'r1',
            role_name: 'Owner',
            is_owner_role: true,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });
    }

    if (path.includes('/platform/workspaces/') && method === 'GET') {
      const id = path.split('/').pop();
      if (id === systemWorkspace.id) {
        return fulfillJson(route, systemWorkspace);
      }
      return fulfillJson(route, { ...fixtureWorkspace, status: workspaceStatus });
    }

    if (path.endsWith('/platform/users') && method === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            id: 'user-1',
            email: 'owner@example.com',
            status: 'active',
            platform_role: 'none',
            created_at: '2026-01-01T00:00:00Z',
            workspace_memberships_count: 1,
          },
        ],
        total: 1,
        limit: 25,
        offset: 0,
      });
    }

    if (path.includes('/platform/users/') && method === 'GET') {
      return fulfillJson(route, {
        id: 'user-1',
        email: 'owner@example.com',
        status: 'active',
        platform_role: 'none',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        email_verified_at: '2026-01-01T00:00:00Z',
        active_session_count: 1,
        memberships: [
          {
            membership_id: 'm1',
            workspace_id: fixtureWorkspace.id,
            workspace_name: fixtureWorkspace.name,
            workspace_slug: fixtureWorkspace.slug,
            workspace_status: workspaceStatus,
            role_id: 'r1',
            role_name: 'Owner',
            is_owner_role: true,
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
      });
    }

    return fulfillJson(route, { code: 'not_found' }, 404);
  });

  await page.goto('/login');
  await page.locator('#email').fill('admin@example.com');
  await page.locator('#password').fill('password123');
  await page.getByTestId('login-submit').click();
  await expect(page.getByTestId('overview-page')).toBeVisible();

  await page.getByTestId('nav-workspaces').click();
  await expect(page.getByTestId('workspaces-page')).toBeVisible();
  await expect(page.getByText('Fixture Acme')).toBeVisible();

  await page.getByTestId('workspace-row').click();
  await expect(page.getByTestId('workspace-detail-page')).toBeVisible();
  await expect(page.getByTestId('workspace-disable-button')).toBeVisible();

  await page.getByTestId('workspace-disable-button').click();
  await expect(page.getByTestId('workspace-disable-dialog')).toBeVisible();
  await page.getByTestId('workspace-disable-dialog-reason').fill('Payment dispute under review');
  await page.getByTestId('workspace-disable-dialog-confirm').click();
  await expect(page.getByText(/Suspended|معلّقة/)).toBeVisible();

  await page.getByTestId('workspace-enable-button').click();
  await page.getByTestId('workspace-enable-dialog-confirm').click();
  await expect(page.getByText(/Active|نشطة/).first()).toBeVisible();

  // System workspace protection
  await page.goto(`/workspaces/${systemWorkspace.id}`);
  await expect(page.getByTestId('workspace-system-protected')).toBeVisible();
  await expect(page.getByTestId('workspace-disable-button')).toHaveCount(0);

  // Users smoke
  await page.getByTestId('nav-users').click();
  await expect(page.getByTestId('users-page')).toBeVisible();
  await page.getByText('owner@example.com').click();
  await expect(page.getByTestId('user-detail-page')).toBeVisible();
  await expect(page.getByTestId('user-memberships-list')).toBeVisible();
  await expect(page.getByText('Fixture Acme')).toBeVisible();
});

test('workspace user cannot enter the Platform Admin dashboard', async ({ page }) => {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path.endsWith('/auth/refresh') && method === 'POST') {
      return fulfillJson(route, { code: 'unauthorized' }, 401);
    }
    if (path.endsWith('/auth/login') && method === 'POST') {
      return fulfillJson(route, {
        access_token: 'e2e-access',
        token_type: 'bearer',
        expires_at: '2099-01-01T00:00:00Z',
        user: workspaceUser,
      });
    }
    if (path.endsWith('/platform/me') && method === 'GET') {
      return fulfillJson(
        route,
        { code: 'platform_admin_required', message: 'Platform admin role required.' },
        403,
      );
    }
    if (path.endsWith('/auth/logout') && method === 'POST') {
      return route.fulfill({ status: 204, body: '' });
    }
    return fulfillJson(route, { code: 'not_found' }, 404);
  });

  await page.goto('/login');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await page.locator('#email').fill('owner@example.com');
  await page.locator('#password').fill('password123');
  await page.getByTestId('login-submit').click();
  await expect(page.getByTestId('platform-access-required')).toBeVisible();
  await expect(page.getByTestId('overview-page')).toHaveCount(0);
});
