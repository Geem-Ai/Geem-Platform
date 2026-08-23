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

const fixtureDashboardSummary = {
  workspaces: { total: 1, active: 1, disabled: 0 },
  users: { total: 2, active: 2, disabled: 0 },
  experts: { published: 1, draft: 0 },
  usage: {
    billed_tokens_24h: 1200,
    billed_tokens_7d: 8400,
    billed_tokens_30d: 42000,
    active_workspaces_30d: 1,
    outstanding_credit_balance: 250,
  },
  billing: {
    active_subscriptions: 1,
    pending_purchases: 0,
    failed_purchases_30d: 0,
    paid_purchase_count_30d: 1,
    paid_purchase_volume_30d: '99.00',
  },
  apps: {
    published: 1,
    active_subscriptions: 0,
    active_licenses: 0,
    installations: 0,
  },
  gateway: {
    gateway_config_id: 'gw-1',
    code: 'clickpay',
    enabled: true,
    test_mode: true,
  },
  recent_activity: [
    {
      id: 'audit-1',
      created_at: '2026-01-02T10:00:00Z',
      actor: { user_id: 'admin-1', email: 'admin@example.com' },
      workspace: { workspace_id: fixtureWorkspace.id, name: fixtureWorkspace.name, slug: fixtureWorkspace.slug },
      action: 'workspace.credit_grant',
      resource: { entity_type: 'credit_ledger_entry', entity_id: 'credit-1' },
      summary: 'E2E grant',
    },
  ],
};

const fixtureUsageSummary = {
  from_day: '2026-01-01',
  to_day: '2026-01-30',
  total_billed_tokens: 42000,
  active_workspaces: 1,
  average_daily_billed_tokens: 1400,
  peak_day: { day: '2026-01-15', billed_tokens: 3000 },
  families: [{ family: 'chat', billed_tokens: 42000, percentage: 100 }],
  sources: [
    { source: 'interactive', billed_tokens: 30000, percentage: 71.43 },
    { source: 'api', billed_tokens: 12000, percentage: 28.57 },
  ],
};

const fixtureUsageTrend = {
  from_day: '2026-01-01',
  to_day: '2026-01-30',
  points: [
    { date: '2026-01-01', billed_tokens: 1000, active_workspaces: 1 },
    { date: '2026-01-15', billed_tokens: 3000, active_workspaces: 1 },
    { date: '2026-01-30', billed_tokens: 1200, active_workspaces: 1 },
  ],
};

const fixtureUsageWorkspaces = {
  items: [
    {
      workspace_id: fixtureWorkspace.id,
      workspace_name: fixtureWorkspace.name,
      workspace_slug: fixtureWorkspace.slug,
      workspace_status: 'active',
      billed_tokens: 42000,
      percentage_of_platform_usage: 100,
      active_days: 20,
      current_plan_code: 'free',
      current_plan_name: 'Free',
    },
  ],
  total: 1,
  limit: 10,
  offset: 0,
  from_day: '2026-01-01',
  to_day: '2026-01-30',
  platform_total_billed_tokens: 42000,
};

const fixtureAuditLogs = {
  items: [
    {
      id: 'audit-1',
      created_at: '2026-01-02T10:00:00Z',
      actor: { user_id: 'admin-1', email: 'admin@example.com' },
      workspace: { workspace_id: fixtureWorkspace.id, name: fixtureWorkspace.name, slug: fixtureWorkspace.slug },
      action: 'workspace.credit_grant',
      resource: { entity_type: 'credit_ledger_entry', entity_id: 'credit-1' },
      summary: 'E2E grant',
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
};

const fixturePlatformExpert = {
  id: 'expert-fixture-1',
  type: 'platform',
  ownership: 'platform',
  workspace_id: null,
  name: 'Fixture Platform Expert',
  description: 'E2E expert',
  icon_url: null,
  status: 'ready',
  visibility: 'platform_published',
  availability_mode: 'selected_workspaces',
  knowledge_mode: 'rag',
  created_by: 'admin-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  knowledge_document_count: 1,
  explicit_workspace_grant_count: 1,
  is_protected: false,
  system_instructions: 'You are a fixture expert.',
  rag_config: { top_k: 10, rerank_top_n: 5, similarity_threshold: 0.5 },
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
    if (path.endsWith('/platform/dashboard/summary') && method === 'GET') {
      return fulfillJson(route, fixtureDashboardSummary);
    }
    if (path.endsWith('/platform/usage/summary') && method === 'GET') {
      return fulfillJson(route, fixtureUsageSummary);
    }
    if (path.endsWith('/platform/usage/trend') && method === 'GET') {
      return fulfillJson(route, fixtureUsageTrend);
    }
    if (path.endsWith('/platform/usage/workspaces') && method === 'GET') {
      return fulfillJson(route, fixtureUsageWorkspaces);
    }
    if (path.includes('/platform/workspaces/') && path.endsWith('/usage/summary') && method === 'GET') {
      return fulfillJson(route, {
        workspace_id: fixtureWorkspace.id,
        workspace_name: fixtureWorkspace.name,
        workspace_slug: fixtureWorkspace.slug,
        workspace_status: workspaceStatus,
        workspace_kind: 'tenant',
        from_day: '2026-01-01',
        to_day: '2026-01-30',
        total_billed_tokens: 42000,
        families: fixtureUsageSummary.families,
        sources: fixtureUsageSummary.sources,
      });
    }
    if (path.includes('/platform/workspaces/') && path.endsWith('/usage/trend') && method === 'GET') {
      return fulfillJson(route, {
        workspace_id: fixtureWorkspace.id,
        from_day: '2026-01-01',
        to_day: '2026-01-30',
        points: fixtureUsageTrend.points,
      });
    }
    if (path.endsWith('/platform/audit-logs') && method === 'GET') {
      return fulfillJson(route, fixtureAuditLogs);
    }
    if (path.includes('/platform/audit-logs/') && method === 'GET') {
      return fulfillJson(route, {
        ...fixtureAuditLogs.items[0],
        metadata: { reason: 'E2E grant', amount: 1000 },
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

    if (path.endsWith('/platform/experts') && method === 'GET') {
      return fulfillJson(route, {
        items: [fixturePlatformExpert],
        total: 1,
        limit: 25,
        offset: 0,
      });
    }

    if (path.includes('/platform/experts/') && path.endsWith('/workspace-grants') && method === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            id: 'grant-1',
            workspace_id: fixtureWorkspace.id,
            workspace_name: fixtureWorkspace.name,
            workspace_slug: fixtureWorkspace.slug,
            workspace_status: fixtureWorkspace.status,
            expert_id: fixturePlatformExpert.id,
            created_by: 'admin-1',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        total: 1,
        limit: 25,
        offset: 0,
      });
    }

    if (path.includes('/platform/experts/') && path.endsWith('/knowledge') && method === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            id: 'link-1',
            expert_id: fixturePlatformExpert.id,
            document_id: 'doc-1',
            source_id: 'src-1',
            created_at: '2026-01-01T00:00:00Z',
            title: 'Fixture notes',
            original_filename: 'notes.txt',
            status: 'ready',
            mime_type: 'text/plain',
            byte_size: 42,
            page_count: 1,
            failure_reason: null,
            source_type: 'upload',
            processed_pages: 1,
            failed_pages: 0,
            current_stage: null,
            progress: 1,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });
    }

    if (path.includes('/platform/experts/') && method === 'GET') {
      return fulfillJson(route, fixturePlatformExpert);
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

    if (path.endsWith('/platform/payment-gateways') && method === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            id: 'gw-clickpay',
            code: 'clickpay',
            display_name: 'ClickPay',
            enabled: true,
            test_mode: true,
            configured: true,
            credential_field_status: {
              profile_id_configured: true,
              server_key_configured: true,
              profile_id: '59020',
            },
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            referenced_purchases_count: 2,
            in_flight_purchases_count: 0,
          },
          {
            id: null,
            code: 'noop',
            display_name: 'Manual / Noop (local)',
            enabled: false,
            test_mode: null,
            configured: false,
            credential_field_status: {},
            created_at: null,
            updated_at: null,
            referenced_purchases_count: 0,
            in_flight_purchases_count: 0,
          },
        ],
        active_gateway_id: 'gw-clickpay',
      });
    }

    if (path.endsWith('/platform/purchases') && method === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            id: 'purchase-1',
            workspace: {
              id: fixtureWorkspace.id,
              name: fixtureWorkspace.name,
              slug: fixtureWorkspace.slug,
            },
            actor: { id: 'user-1', email: 'owner@example.com' },
            kind: 'credit_pack',
            status: 'paid',
            amount: '25.00',
            currency: 'SAR',
            gateway_code: 'noop',
            gateway_config_id: 'gw-noop',
            cart_id: 'cart-1',
            tran_ref: 'noop_ref',
            target: {
              kind: 'credit_pack',
              item_name: 'Starter Pack',
              item_code: 'starter',
              credits: 1000,
            },
            paid_at: '2026-01-02T00:00:00Z',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-02T00:00:00Z',
            reconcile_eligible: false,
            invoice_available: true,
          },
        ],
        total: 1,
        limit: 25,
        offset: 0,
      });
    }

    if (path.includes('/platform/purchases/') && method === 'GET') {
      return fulfillJson(route, {
        id: 'purchase-1',
        workspace: {
          id: fixtureWorkspace.id,
          name: fixtureWorkspace.name,
          slug: fixtureWorkspace.slug,
        },
        actor: { id: 'user-1', email: 'owner@example.com' },
        kind: 'credit_pack',
        status: 'paid',
        amount: '25.00',
        currency: 'SAR',
        target: {
          kind: 'credit_pack',
          item_name: 'Starter Pack',
          item_code: 'starter',
          credits: 1000,
        },
        gateway: {
          code: 'noop',
          display_name: 'Manual / Noop (local)',
          gateway_config_id: 'gw-noop',
          cart_id: 'cart-1',
          tran_ref: 'noop_ref',
        },
        fulfillment: {
          fulfilled: true,
          invoice_available: true,
          invoice_number: 'GEEM-000001',
        },
        paid_at: '2026-01-02T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
        reconcile_eligible: false,
      });
    }

    return fulfillJson(route, { code: 'not_found' }, 404);
  });

  await page.goto('/login');
  await page.locator('#email').fill('admin@example.com');
  await page.locator('#password').fill('password123');
  await page.getByTestId('login-submit').click();
  await expect(page.getByTestId('overview-page')).toBeVisible();
  await expect(page.getByTestId('overview-billing-card')).toBeVisible();
  await expect(page.getByText('42,000')).toBeVisible();

  await page.getByTestId('nav-usage').click();
  await expect(page.getByTestId('usage-page')).toBeVisible();
  await page.getByTestId('usage-preset-30').click();
  await expect(page.getByText('Fixture Acme')).toBeVisible();

  await page.getByTestId('nav-audit-logs').click();
  await expect(page.getByTestId('audit-logs-page')).toBeVisible();
  await page.getByRole('button', { name: 'Details' }).click();
  await expect(page.getByText('E2E grant', { exact: true }).first()).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByTestId('nav-workspaces').click();
  await expect(page.getByTestId('workspaces-page')).toBeVisible();
  await expect(page.getByText('Fixture Acme')).toBeVisible();

  await page.getByTestId('workspace-row').click();
  await expect(page.getByTestId('workspace-detail-page')).toBeVisible();
  await expect(page.getByTestId('workspace-disable-button')).toBeVisible();
  await expect(page.getByTestId('workspace-billing-section')).toBeVisible();
  await expect(page.getByTestId('workspace-usage-section')).toBeVisible();
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
  await expect(page.getByTestId('plans-list')).toBeVisible();
  expect(
    await page.getByTestId('plans-list').evaluate((element) => (
      element.scrollWidth <= element.clientWidth
    )),
  ).toBe(true);
  await expect(page.getByText('Free', { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId('plan-bootstrap-badge').first()).toBeVisible();
  await page.getByText('Free', { exact: true }).first().click();
  await expect(page.getByTestId('plan-detail-page')).toBeVisible();
  await expect(page.getByTestId('plan-bootstrap-protected')).toBeVisible();
  await expect(page.getByTestId('plan-deactivate-button')).toHaveCount(0);

  // Platform Experts smoke (12D)
  await page.getByTestId('nav-platform-experts').click();
  await expect(page.getByTestId('experts-page')).toBeVisible();
  await expect(page.getByText('Fixture Platform Expert')).toBeVisible();
  await page.getByTestId(`expert-row-${fixturePlatformExpert.id}`).click();
  await expect(page.getByTestId('expert-detail-page')).toBeVisible();
  await expect(page.getByTestId('expert-detail-instructions')).toHaveValue(
    'You are a fixture expert.',
  );
  await expect(page.getByTestId('knowledge-item-doc-1')).toBeVisible();

  // Credits smoke
  await page.getByTestId('nav-credits').click();
  await expect(page.getByTestId('credits-page')).toBeVisible();
  await page.getByTestId('credits-workspace-row').click();
  await expect(page.getByTestId('credits-balance')).toBeVisible();
  await expect(page.getByTestId('credits-history-list')).toBeVisible();
  expect(
    await page.getByTestId('credits-history-list').evaluate((element) => (
      element.scrollWidth <= element.clientWidth
    )),
  ).toBe(true);
  await page.getByTestId('credits-open-account').click();
  await expect(page.getByTestId('credit-detail-page')).toBeVisible();
  await expect(page.getByTestId('credit-detail-summary')).toBeVisible();
  await expect(page.getByTestId('credit-detail-history-list')).toBeVisible();
  expect(
    await page.getByTestId('credit-detail-history-list').evaluate((element) => (
      element.scrollWidth <= element.clientWidth
    )),
  ).toBe(true);

  // Payment gateways + purchases smoke (12F)
  await page.getByTestId('nav-payment-gateways').click();
  await expect(page.getByTestId('payment-gateways-page')).toBeVisible();
  await expect(page.getByTestId('gateway-summary')).toBeVisible();
  await expect(page.getByTestId('gateway-info-banner')).toBeVisible();
  await expect(page.getByTestId('gateway-card-clickpay')).toBeVisible();
  await expect(page.getByTestId('gateway-card-noop')).toBeVisible();

  await page.getByTestId('nav-purchases').click();
  await expect(page.getByTestId('purchases-page')).toBeVisible();
  await expect(page.getByTestId('purchases-list')).toBeVisible();
  await page.getByTestId('purchase-row-purchase-1').getByRole('link').first().click();
  await expect(page.getByTestId('purchase-detail-page')).toBeVisible();
  await expect(page.getByTestId('purchase-download-invoice')).toBeVisible();

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

test('RTL overview and workspaces render with dir=rtl', async ({ page }) => {
  let loggedIn = false;

  await page.addInitScript(() => {
    localStorage.setItem('geem-admin-locale', 'ar');
    localStorage.setItem('geem-admin-theme', 'light');
  });

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
      return fulfillJson(route, {
        user: adminUser,
        platform_role: 'admin',
        authorized: true,
      });
    }
    if (path.endsWith('/platform/dashboard/summary') && method === 'GET') {
      return fulfillJson(route, fixtureDashboardSummary);
    }
    if (path.endsWith('/platform/workspaces') && method === 'GET') {
      return fulfillJson(route, {
        items: [fixtureWorkspace],
        total: 1,
        limit: 25,
        offset: 0,
      });
    }
    if (path.endsWith('/auth/logout') && method === 'POST') {
      loggedIn = false;
      return route.fulfill({ status: 204, body: '' });
    }
    return fulfillJson(route, { code: 'not_found' }, 404);
  });

  await page.goto('/login');
  await page.locator('#email').fill('admin@example.com');
  await page.locator('#password').fill('password123');
  await page.getByTestId('login-submit').click();

  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByTestId('overview-page')).toBeVisible();
  await expect(page.getByTestId('overview-metrics')).toBeVisible();

  await page.getByTestId('nav-workspaces').click();
  await expect(page.getByTestId('workspaces-page')).toBeVisible();
  await expect(page.getByText('Fixture Acme')).toBeVisible();
});
