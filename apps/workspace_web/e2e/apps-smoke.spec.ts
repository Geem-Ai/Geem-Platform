import { expect, test, type Page, type Route } from '@playwright/test';

const workspaceId = 'ws-e2e-9g';
const user = {
  id: 'user-1',
  email: 'owner@example.com',
  display_name: 'Owner',
};

function driveApp(canInstall = true) {
  return {
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
    can_install: canInstall,
    can_uninstall: false,
    access_requirement: 'free',
    access: {
      status: canInstall ? 'entitled_not_installed' : 'entitled_not_installed',
      plan_id: 'plan-free',
      plan_code: 'free',
      plan_name: 'Free',
      current_period_start: null,
      current_period_end: null,
      commercially_entitled: true,
      can_purchase: false,
      can_renew: false,
      can_install: canInstall,
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
}

function whatsappApp() {
  return {
    ...driveApp(false),
    id: 'app-wa',
    slug: 'whatsapp',
    name: 'WhatsApp',
    short_description: 'WhatsApp channel',
    billing_type: 'subscription',
    access_requirement: 'subscription',
    can_install: false,
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
}

function agentsAiApp() {
  return {
    ...driveApp(false),
    id: 'app-agents-ai',
    slug: 'agents-ai',
    name: 'Agents AI',
    short_description: 'Client-owned agent loops with Geem RAG.',
    description: 'OpenAI-compatible Agent API.',
    billing_type: 'subscription',
    status: 'published',
    installation: { id: 'install-agents', status: 'active' },
    installation_status: 'active',
    access_requirement: 'subscription',
    can_install: false,
    can_uninstall: true,
    access: {
      status: 'active',
      plan_id: 'plan-agents-team',
      plan_code: 'agents-team',
      plan_name: 'Agents Team',
      current_period_start: '2026-08-01T00:00:00Z',
      current_period_end: '2026-09-01T00:00:00Z',
      commercially_entitled: true,
      can_purchase: false,
      can_renew: true,
      can_install: false,
      can_uninstall: true,
    },
    plans: [
      {
        id: 'plan-agents-team',
        code: 'agents-team',
        name: 'Agents Team',
        description: 'Team request allowance',
        billing_interval: 'monthly',
        price_amount: '149.00',
        currency: 'SAR',
        is_default: true,
        entitlements: { agent_requests_daily: 500 },
      },
    ],
    connector: null,
  };
}

function agentsAiUsage() {
  return {
    access: {
      status: 'active',
      plan_id: 'plan-agents-team',
      plan_code: 'agents-team',
      plan_name: 'Agents Team',
      plan_price_amount: '149.00',
      plan_currency: 'SAR',
      plan_billing_interval: 'monthly',
      current_period_start: '2026-08-01T00:00:00Z',
      current_period_end: '2026-09-01T00:00:00Z',
      commercially_entitled: true,
      installed: true,
    },
    agent_requests_daily: {
      used: 73,
      limit: 500,
      reset_at: '2026-08-26T00:00:00Z',
    },
    base_url: 'https://api.geem.test/api/v1/agent',
    model: 'dalseen/geem-1.0',
  };
}

function workspace(role: 'owner' | 'admin' | 'member') {
  const isOwner = role === 'owner';
  return {
    id: workspaceId,
    name: 'E2E Workspace',
    slug: 'e2e',
    status: 'active',
    role: {
      id: `role-${role}`,
      name: role === 'admin' ? 'Administrator' : role === 'owner' ? 'Owner' : 'Member',
      is_system: true,
      is_owner_role: isOwner,
      system_key: role,
    },
    permissions: isOwner
      ? []
      : ['workspace.view', 'apps.view', 'chat.use', 'experts.view'],
    kind: 'tenant',
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockAuthenticatedApp(page: Page, role: 'owner' | 'member' = 'owner') {
  const ws = workspace(role);
  const me = {
    user,
    workspaces: [ws],
    current_workspace: ws,
  };

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path.endsWith('/auth/refresh') && method === 'POST') {
      return fulfillJson(route, { access_token: 'e2e-access', user });
    }
    if (path.endsWith('/auth/me') && method === 'GET') {
      return fulfillJson(route, me);
    }
    if (path.endsWith('/workspaces') && method === 'GET') {
      return fulfillJson(route, [ws]);
    }
    if (path.endsWith('/apps/categories')) {
      return fulfillJson(route, [
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
      ]);
    }
    if (path.endsWith('/apps/installations')) {
      return fulfillJson(route, { items: [], total: 0, limit: 50, offset: 0 });
    }
    if (path.endsWith('/apps/google-drive')) {
      return fulfillJson(route, driveApp(role !== 'member'));
    }
    if (path.endsWith('/apps/whatsapp')) {
      const app = whatsappApp();
      if (role === 'member') {
        app.access = { ...app.access, can_purchase: false };
      }
      return fulfillJson(route, app);
    }
    if (path.endsWith('/apps/agents-ai/usage')) {
      return fulfillJson(route, agentsAiUsage());
    }
    if (path.endsWith('/apps/agents-ai')) {
      return fulfillJson(route, agentsAiApp());
    }
    if (path.includes('/apps/') && path.includes('/connections')) {
      return fulfillJson(route, {
        items: [],
        total: 0,
        limit: 50,
        offset: 0,
        used: 0,
        connection_limit: 1,
      });
    }
    if (path.endsWith('/apps') || /\/apps\?/.test(path)) {
      const canInstall = role !== 'member';
      return fulfillJson(route, {
        items: [driveApp(canInstall), whatsappApp(), agentsAiApp()],
        total: 3,
        limit: 50,
        offset: 0,
      });
    }

    return fulfillJson(route, {});
  });
}

test.describe('Apps Phase 9G browser smoke', () => {
  test('catalog shows free and subscription apps', async ({ page }) => {
    await mockAuthenticatedApp(page, 'owner');
    await page.goto('/apps');
    await expect(page.getByTestId('apps-page')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('app-card-google-drive').first()).toBeVisible();
    await expect(page.getByTestId('app-card-whatsapp').first()).toBeVisible();
  });

  test('installed apps empty state', async ({ page }) => {
    await mockAuthenticatedApp(page, 'owner');
    await page.goto('/apps/installed');
    await expect(page.getByTestId('installed-apps-page')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('installed-empty')).toBeVisible();
  });

  test('member sees read-only hint on installed page', async ({ page }) => {
    await mockAuthenticatedApp(page, 'member');
    await page.goto('/apps/installed');
    await expect(page.getByTestId('installed-member-hint')).toBeVisible({
      timeout: 15_000,
    });
  });

  test('whatsapp detail shows plan cards for owner', async ({ page }) => {
    await mockAuthenticatedApp(page, 'owner');
    await page.goto('/apps/whatsapp');
    await expect(page.getByTestId('app-detail-sheet')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('app-plan-line')).toBeVisible();
    await expect(page.getByTestId('app-plan-desk')).toBeVisible();
  });

  test('Agents AI detail shows paid access, usage, and integrator endpoints', async ({
    page,
  }) => {
    await mockAuthenticatedApp(page, 'owner');
    await page.goto('/apps/agents-ai');
    await expect(page.getByTestId('agents-ai-panel')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('agents-ai-access-active')).toBeVisible();
    await expect(page.getByTestId('agents-ai-daily-usage')).toContainText('73');
    await expect(
      page.getByText('https://api.geem.test/api/v1/agent', { exact: true }),
    ).toBeVisible();
    await expect(page.getByText('dalseen/geem-1.0')).toBeVisible();
    await expect(
      page.getByText('Installed. Integration setup will be available in a later phase.'),
    ).toHaveCount(0);
  });
});
