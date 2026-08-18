import { expect, test, type Page } from '@playwright/test';

const workspaceId = 'ws-e2e-9g';

const driveApp = {
  id: 'app-drive',
  slug: 'google-drive',
  name: 'Google Drive',
  short_description: 'Connect Drive',
  description: 'Drive description',
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
  plans: [
    {
      id: 'plan-free',
      code: 'free',
      name: 'Free',
      description: null,
      billing_interval: 'none',
      price_amount: '0.00',
      currency: 'SAR',
      is_default: true,
      entitlements: { connections: 1 },
    },
  ],
  installation: null,
  installation_status: null,
  can_install: true,
  can_uninstall: false,
  access_requirement: 'free',
  access: {
    status: 'entitled_not_installed',
    plan_id: 'plan-free',
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
    available: true,
    auth_mode: 'oauth2',
    can_connect: true,
    supports_sync: true,
    supports_webhooks: true,
    supports_health_check: true,
  },
  has_active_connection: false,
  connection_status: null,
  connection_usage: null,
  connections: [],
};

const whatsappApp = {
  ...driveApp,
  id: 'app-wa',
  slug: 'whatsapp',
  name: 'WhatsApp',
  short_description: 'WhatsApp channel',
  billing_type: 'subscription',
  is_featured: true,
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
    {
      id: 'plan-desk',
      code: 'desk',
      name: 'WhatsApp Desk',
      description: 'Three connections',
      billing_interval: 'monthly',
      price_amount: '199.00',
      currency: 'SAR',
      is_default: false,
      entitlements: { connections: 3 },
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
};

async function mockWorkspaceShell(page: Page, role: 'owner' | 'member' = 'owner') {
  await page.addInitScript(
    ({ workspaceId: ws, role: r }) => {
      window.localStorage.setItem(
        'geem.auth',
        JSON.stringify({
          access_token: 'e2e-token',
          refresh_token: 'e2e-refresh',
        }),
      );
      window.localStorage.setItem('geem.workspaceId', ws);
      window.localStorage.setItem('geem.workspaceRole', r);
    },
    { workspaceId, role },
  );

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path === '/api/auth/me' || path.endsWith('/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user-1',
          email: 'owner@example.com',
          display_name: 'Owner',
        }),
      });
    }

    if (path.endsWith('/workspaces') && route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: workspaceId,
              name: 'E2E Workspace',
              slug: 'e2e',
              role,
              kind: 'tenant',
            },
          ],
        }),
      });
    }

    if (path.includes(`/workspaces/${workspaceId}`) || path.endsWith('/workspaces/current')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: workspaceId,
          name: 'E2E Workspace',
          slug: 'e2e',
          role,
          kind: 'tenant',
        }),
      });
    }

    if (path.endsWith('/apps/categories')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            slug: 'knowledge',
            name_key: 'apps.categories.knowledge',
            description_key: null,
            icon: null,
            sort_order: 10,
          },
        ]),
      });
    }

    if (path.endsWith('/apps/installations')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }),
      });
    }

    if (path.endsWith('/apps/google-drive')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(driveApp),
      });
    }

    if (path.endsWith('/apps/whatsapp')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(whatsappApp),
      });
    }

    if (path.endsWith('/apps') || path.includes('/apps?')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [driveApp, whatsappApp],
          total: 2,
          limit: 50,
          offset: 0,
        }),
      });
    }

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    });
  });
}

test.describe('Apps Phase 9G browser smoke', () => {
  test('catalog shows free and subscription apps', async ({ page }) => {
    await mockWorkspaceShell(page, 'owner');
    await page.goto('/apps');
    await expect(page.getByTestId('apps-page')).toBeVisible();
    await expect(page.getByTestId('app-card-google-drive').first()).toBeVisible();
    await expect(page.getByTestId('app-card-whatsapp').first()).toBeVisible();
  });

  test('installed apps empty state', async ({ page }) => {
    await mockWorkspaceShell(page, 'owner');
    await page.goto('/apps/installed');
    await expect(page.getByTestId('installed-apps-page')).toBeVisible();
    await expect(page.getByTestId('installed-empty')).toBeVisible();
  });

  test('member sees read-only hint on installed page', async ({ page }) => {
    await mockWorkspaceShell(page, 'member');
    await page.goto('/apps/installed');
    await expect(page.getByTestId('installed-member-hint')).toBeVisible();
  });

  test('whatsapp detail shows plan cards for owner', async ({ page }) => {
    await mockWorkspaceShell(page, 'owner');
    await page.goto('/apps/whatsapp');
    await expect(page.getByTestId('app-detail-sheet')).toBeVisible();
    await expect(page.getByTestId('app-plan-line')).toBeVisible();
    await expect(page.getByTestId('app-plan-desk')).toBeVisible();
  });
});
