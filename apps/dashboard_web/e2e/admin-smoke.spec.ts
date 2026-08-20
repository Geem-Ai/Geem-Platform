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

const fixturePlan = {
  id: 'plan-1',
  code: 'free',
  name: 'Free',
  description: 'Bootstrap free plan',
  status: 'active',
  price_amount: null,
  currency: 'SAR',
  is_bootstrap: true,
  is_commercial: false,
  subscriber_count: 1,
  entitlements: [
    { key: 'ai_tokens_daily', value: 1000, value_type: 'integer' },
    { key: 'ai_tokens_weekly', value: 5000, value_type: 'integer' },
    { key: 'ai_tokens_monthly', value: 20000, value_type: 'integer' },
    { key: 'experts_limit', value: 3, value_type: 'integer' },
    { key: 'storage_bytes', value: 1073741824, value_type: 'integer' },
    { key: 'api_requests_per_minute', value: 60, value_type: 'integer' },
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const fixtureProPlan = {
  ...fixturePlan,
  id: 'plan-2',
  code: 'pro',
  name: 'Pro',
  description: 'Commercial plan',
  price_amount: '99.00',
  is_bootstrap: false,
  is_commercial: true,
  subscriber_count: 0,
  entitlements: [
    { key: 'ai_tokens_daily', value: 10000, value_type: 'integer' },
    { key: 'ai_tokens_weekly', value: 50000, value_type: 'integer' },
    { key: 'ai_tokens_monthly', value: 200000, value_type: 'integer' },
    { key: 'experts_limit', value: 20, value_type: 'integer' },
    { key: 'storage_bytes', value: 10737418240, value_type: 'integer' },
    { key: 'api_requests_per_minute', value: 120, value_type: 'integer' },
  ],
};

const entitlementCatalog = {
  items: [
    { key: 'ai_tokens_daily', value_type: 'integer', unit: 'tokens' },
    { key: 'ai_tokens_weekly', value_type: 'integer', unit: 'tokens' },
    { key: 'ai_tokens_monthly', value_type: 'integer', unit: 'tokens' },
    { key: 'experts_limit', value_type: 'integer', unit: 'experts' },
    { key: 'storage_bytes', value_type: 'integer', unit: 'bytes' },
    { key: 'api_requests_per_minute', value_type: 'integer', unit: 'requests_per_minute' },
  ],
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

    if (path.includes('/platform/workspaces/') && path.endsWith('/subscription/assign') && method === 'POST') {
      return fulfillJson(route, {
        subscription_id: 'sub-2',
        status: 'active',
        plan_id: fixtureProPlan.id,
        plan_code: fixtureProPlan.code,
        plan_name: fixtureProPlan.name,
        plan_status: 'active',
        starts_at: '2026-01-01T00:00:00Z',
        current_period_start: '2026-01-01T00:00:00Z',
        current_period_end: '2026-02-01T00:00:00Z',
        ends_at: null,
        source: 'platform_admin',
        created_at: '2026-01-01T00:00:00Z',
      });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/subscription') && method === 'GET') {
      return fulfillJson(route, {
        subscription_id: 'sub-1',
        status: 'active',
        plan_id: fixturePlan.id,
        plan_code: fixturePlan.code,
        plan_name: fixturePlan.name,
        plan_status: 'active',
        starts_at: '2026-01-01T00:00:00Z',
        current_period_start: '2026-01-01T00:00:00Z',
        current_period_end: '2026-02-01T00:00:00Z',
        ends_at: null,
        source: 'bootstrap',
        created_at: '2026-01-01T00:00:00Z',
      });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/entitlements') && method === 'GET') {
      return fulfillJson(route, {
        workspace_id: fixtureWorkspace.id,
        subscription_id: 'sub-1',
        plan_id: fixturePlan.id,
        plan_code: fixturePlan.code,
        plan_name: fixturePlan.name,
        plan_status: 'active',
        items: fixturePlan.entitlements,
      });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/usage') && method === 'GET') {
      return fulfillJson(route, {
        ai_tokens_daily: { limit: 1000, used: 10, reserved: 0, remaining: 990 },
        ai_tokens_weekly: { limit: 5000, used: 10, reserved: 0, remaining: 4990 },
        ai_tokens_monthly: { limit: 20000, used: 10, reserved: 0, remaining: 19990 },
        experts: { limit: 3, used: 1, reserved: 0, remaining: 2 },
        storage_bytes: {
          limit: 1073741824,
          used: 0,
          reserved: 0,
          remaining: 1073741824,
        },
        credit_balance: 250,
      });
    }

    if (
      path.includes('/platform/workspaces/') &&
      path.endsWith('/credits/grant') &&
      method === 'POST'
    ) {
      return fulfillJson(route, {
        workspace_id: fixtureWorkspace.id,
        balance: 350,
        entry: {
          id: 'cle-1',
          entry_type: 'grant',
          amount: 100,
          remaining_amount: 100,
          request_id: 'platform-credit-grant:test',
          source_type: 'platform_admin',
          source_id: null,
          reason: 'E2E grant',
          created_at: '2026-01-01T00:00:00Z',
        },
        idempotent_replay: false,
      });
    }

    if (
      path.includes('/platform/workspaces/') &&
      path.includes('/credits/history') &&
      method === 'GET'
    ) {
      return fulfillJson(route, {
        items: [
          {
            id: 'cle-0',
            entry_type: 'grant',
            amount: 250,
            remaining_amount: 250,
            request_id: null,
            source_type: 'platform_admin',
            source_id: null,
            reason: 'Seed',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      });
    }

    if (path.includes('/platform/workspaces/') && path.endsWith('/credits') && method === 'GET') {
      return fulfillJson(route, {
        workspace_id: fixtureWorkspace.id,
        balance: 250,
        recent: [],
      });
    }

    if (path.endsWith('/platform/entitlement-catalog') && method === 'GET') {
      return fulfillJson(route, entitlementCatalog);
    }

    if (path.endsWith('/platform/plans') && method === 'GET') {
      return fulfillJson(route, {
        items: [fixturePlan, fixtureProPlan],
        total: 2,
        limit: 100,
        offset: 0,
      });
    }

    if (path.includes('/platform/plans/') && method === 'GET') {
      const id = path.split('/').pop();
      if (id === fixtureProPlan.id) return fulfillJson(route, fixtureProPlan);
      return fulfillJson(route, fixturePlan);
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
  await expect(page.getByTestId('workspace-billing-section')).toBeVisible();
  await expect(page.getByTestId('workspace-change-plan-button')).toBeVisible();

  await page.getByTestId('workspace-grant-credits-button').click();
  await expect(page.getByTestId('grant-credits-dialog')).toBeVisible();
  await page.getByTestId('grant-credits-amount').fill('100');
  await page.getByTestId('grant-credits-reason').fill('E2E grant');
  await page.getByTestId('grant-credits-continue').click();
  await page.getByTestId('grant-credits-confirm').click();
  await expect(page.getByTestId('grant-credits-dialog')).toHaveCount(0);

  await page.getByTestId('workspace-disable-button').click();
  await expect(page.getByTestId('workspace-disable-dialog')).toBeVisible();
  await page.getByTestId('workspace-disable-dialog-reason').fill('Payment dispute under review');
  await page.getByTestId('workspace-disable-dialog-confirm').click();
  await expect(page.getByText(/Suspended|معلّقة/).first()).toBeVisible();

  await page.getByTestId('workspace-enable-button').click();
  await page.getByTestId('workspace-enable-dialog-confirm').click();
  await expect(page.getByText(/Active|نشطة/).first()).toBeVisible();

  // System workspace protection
  await page.goto(`/workspaces/${systemWorkspace.id}`);
  await expect(page.getByTestId('workspace-system-protected')).toBeVisible();
  await expect(page.getByTestId('workspace-disable-button')).toHaveCount(0);
  await expect(page.getByTestId('workspace-billing-system')).toBeVisible();

  // Plans smoke
  await page.getByTestId('nav-plans').click();
  await expect(page.getByTestId('plans-page')).toBeVisible();
  await expect(page.getByText('Free', { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId('plan-bootstrap-badge').first()).toBeVisible();
  await page.getByText('Free', { exact: true }).first().click();
  await expect(page.getByTestId('plan-detail-page')).toBeVisible();
  await expect(page.getByTestId('plan-bootstrap-protected')).toBeVisible();
  await expect(page.getByTestId('plan-deactivate-button')).toHaveCount(0);

  // Credits smoke
  await page.getByTestId('nav-credits').click();
  await expect(page.getByTestId('credits-page')).toBeVisible();
  await page.getByTestId('credits-workspace-row').click();
  await expect(page.getByTestId('credits-balance')).toBeVisible();
  await expect(page.getByTestId('credits-history-list')).toBeVisible();

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
