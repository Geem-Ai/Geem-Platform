import { expect, test, type Page, type Route } from '@playwright/test';

const workspaceId = 'ws-e2e-10c';
const inviteToken = 'e2e-rbac-invite-token';

const owner = {
  id: 'user-owner',
  email: 'owner@example.com',
  status: 'active',
  platform_role: 'none',
  created_at: '2026-01-01T00:00:00Z',
};

const agent = {
  id: 'user-agent',
  email: 'agent@example.com',
  status: 'active',
  platform_role: 'none',
  created_at: '2026-01-02T00:00:00Z',
};

type RoleRow = {
  id: string;
  name: string;
  is_system: boolean;
  is_owner_role: boolean;
  system_key: string | null;
  workspace_id: string;
  description: string | null;
  permissions: string[];
  assigned_count: number;
  created_at: string;
  updated_at: string;
};

const ownerRole: RoleRow = {
  id: 'role-owner',
  name: 'Owner',
  is_system: true,
  is_owner_role: true,
  system_key: 'owner',
  workspace_id: workspaceId,
  description: null,
  permissions: [],
  assigned_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const memberRole: RoleRow = {
  id: 'role-member',
  name: 'Member',
  is_system: true,
  is_owner_role: false,
  system_key: 'member',
  workspace_id: workspaceId,
  description: null,
  permissions: ['workspace.view', 'chat.use', 'experts.view'],
  assigned_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const LIMITED = ['workspace.view', 'chat.use', 'experts.view'];
const LIMITED_PLUS_BILLING = [...LIMITED, 'billing.view'];

const catalog = [
  {
    key: 'workspace.view',
    group: 'workspace',
    name_key: 'permissions.workspace.view.name',
    description_key: 'permissions.workspace.view.description',
    owner_only: false,
  },
  {
    key: 'chat.use',
    group: 'chat',
    name_key: 'permissions.chat.use.name',
    description_key: 'permissions.chat.use.description',
    owner_only: false,
  },
  {
    key: 'experts.view',
    group: 'experts',
    name_key: 'permissions.experts.view.name',
    description_key: 'permissions.experts.view.description',
    owner_only: false,
  },
  {
    key: 'billing.view',
    group: 'billing',
    name_key: 'permissions.billing.view.name',
    description_key: 'permissions.billing.view.description',
    owner_only: false,
  },
];

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function workspaceFor(role: RoleRow, permissions: string[]) {
  return {
    id: workspaceId,
    name: 'RBAC Workspace',
    slug: 'rbac',
    status: 'active',
    role: {
      id: role.id,
      name: role.name,
      is_system: role.is_system,
      is_owner_role: role.is_owner_role,
      system_key: role.system_key,
    },
    permissions,
    kind: 'tenant',
  };
}

test('limited Support Agent sidebar, 403, and live permission update', async ({
  browser,
}) => {
  const roles: RoleRow[] = [ownerRole, memberRole];
  const members = [
    {
      id: 'mem-owner',
      user_id: owner.id,
      email: owner.email,
      role: ownerRole,
      created_at: '2026-01-01T00:00:00Z',
    },
  ];
  const invitations: Array<{
    id: string;
    workspace_id: string;
    email: string;
    role: RoleRow;
    status: string;
    expires_at: string;
    created_at: string;
    invited_by: { id: string; email: string };
  }> = [];
  let supportPerms = [...LIMITED];
  let session: 'owner' | 'agent' | 'guest' = 'owner';

  async function mockApi(page: Page) {
    await page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      const method = route.request().method();
      const actor = session === 'owner' ? owner : session === 'agent' ? agent : null;
      const currentRole = session === 'agent' ? roles.find((row) => row.name === 'Support Agent') ?? memberRole : ownerRole;
      const currentPerms =
        session === 'agent'
          ? supportPerms
          : [
              'workspace.view',
              'chat.use',
              'experts.view',
              'members.view',
              'members.invite',
              'roles.view',
              'roles.manage',
              'billing.view',
            ];
      const ws = actor ? workspaceFor(currentRole, currentPerms) : null;

      if (path.endsWith('/auth/refresh') && method === 'POST') {
        if (!actor) return fulfillJson(route, { code: 'unauthorized' }, 401);
        return fulfillJson(route, {
          access_token: `e2e-${actor.id}`,
          token_type: 'bearer',
          expires_at: '2027-01-01T00:00:00Z',
          user: actor,
        });
      }
      if ((path.endsWith('/auth/login') || path.endsWith('/auth/register')) && method === 'POST') {
        const body = route.request().postDataJSON() as { email?: string };
        session = body.email === agent.email ? 'agent' : 'owner';
        const user = session === 'agent' ? agent : owner;
        return fulfillJson(route, {
          access_token: `e2e-${user.id}`,
          token_type: 'bearer',
          expires_at: '2027-01-01T00:00:00Z',
          user,
        });
      }
      if (path.endsWith('/auth/me') && method === 'GET') {
        if (!actor) return fulfillJson(route, { code: 'unauthorized' }, 401);
        return fulfillJson(route, {
          user: actor,
          workspaces: ws ? [ws] : [],
          current_workspace: ws,
          membership: ws
            ? {
                id: `mem-${actor.id}`,
                workspace_id: ws.id,
                user_id: actor.id,
                role: ws.role,
                created_at: '2026-01-01T00:00:00Z',
                permissions: ws.permissions,
              }
            : null,
        });
      }
      if (path.endsWith('/workspaces') && method === 'GET') {
        return fulfillJson(route, ws ? [ws] : []);
      }
      if (path.includes(`/workspaces/${workspaceId}/permissions`) && method === 'GET') {
        return fulfillJson(route, { items: catalog });
      }
      if (path.includes(`/workspaces/${workspaceId}/roles/assignable`) && method === 'GET') {
        return fulfillJson(route, {
          items: roles.filter((row) => !row.is_owner_role),
        });
      }
      if (path.match(/\/workspaces\/[^/]+\/roles\/[^/]+$/) && method === 'PATCH') {
        const roleId = path.split('/').at(-1);
        const body = route.request().postDataJSON() as { permissions?: string[] };
        const role = roles.find((row) => row.id === roleId);
        if (!role) return fulfillJson(route, { code: 'role_not_found' }, 404);
        role.permissions = body.permissions ?? role.permissions;
        if (role.name === 'Support Agent') supportPerms = [...role.permissions];
        return fulfillJson(route, role);
      }
      if (path.includes(`/workspaces/${workspaceId}/roles`) && method === 'POST') {
        const body = route.request().postDataJSON() as {
          name: string;
          description?: string | null;
          permissions: string[];
        };
        const created: RoleRow = {
          id: 'role-support',
          name: body.name,
          is_system: false,
          is_owner_role: false,
          system_key: null,
          workspace_id: workspaceId,
          description: body.description ?? null,
          permissions:
            body.permissions && body.permissions.length > 0
              ? body.permissions
              : [...LIMITED],
          assigned_count: 0,
          created_at: '2026-08-18T12:00:00Z',
          updated_at: '2026-08-18T12:00:00Z',
        };
        roles.push(created);
        supportPerms = [...created.permissions];
        return fulfillJson(route, created, 201);
      }
      if (path.includes(`/workspaces/${workspaceId}/roles`) && method === 'GET') {
        return fulfillJson(route, { items: roles });
      }
      if (path.includes(`/workspaces/${workspaceId}/members`) && method === 'GET') {
        return fulfillJson(route, members);
      }
      if (path.includes(`/workspaces/${workspaceId}/invitations`) && method === 'POST') {
        const body = route.request().postDataJSON() as { email?: string; role_id?: string };
        const invited = roles.find((row) => row.id === body.role_id) ?? memberRole;
        const item = {
          id: 'inv-support',
          workspace_id: workspaceId,
          email: (body.email ?? '').toLowerCase(),
          role: invited,
          status: 'pending',
          expires_at: '2026-08-21T12:00:00Z',
          created_at: '2026-08-18T12:00:00Z',
          invited_by: { id: owner.id, email: owner.email },
        };
        invitations.push(item);
        return fulfillJson(route, item, 201);
      }
      if (path.includes(`/workspaces/${workspaceId}/invitations`) && method === 'GET') {
        return fulfillJson(route, {
          items: invitations,
          total: invitations.length,
          limit: 50,
          offset: 0,
        });
      }
      if (path.endsWith('/invitations/accept') && method === 'POST') {
        const support = roles.find((row) => row.name === 'Support Agent') ?? memberRole;
        members.push({
          id: 'mem-agent',
          user_id: agent.id,
          email: agent.email,
          role: support,
          created_at: '2026-08-18T12:00:00Z',
        });
        invitations.splice(0, invitations.length);
        return fulfillJson(route, {
          invitation_id: 'inv-support',
          workspace_id: workspaceId,
          workspace_name: 'RBAC Workspace',
          workspace_slug: 'rbac',
          role: support,
          membership_id: 'mem-agent',
          already_member: false,
        });
      }
      if (path.includes('/conversations')) {
        return fulfillJson(route, []);
      }
      if (path.includes('/experts')) {
        return fulfillJson(route, []);
      }
      if (path.endsWith('/usage/summary')) {
        const meter = {
          limit: 1000,
          used: 0,
          reserved: 0,
          remaining: 1000,
          period_start: '2026-08-01T00:00:00Z',
          period_end: '2026-09-01T00:00:00Z',
        };
        return fulfillJson(route, {
          ai_tokens: { daily: meter, weekly: meter, monthly: meter },
          ai: { daily: meter, weekly: meter, monthly: meter },
          experts: meter,
          storage_bytes: meter,
          storage: {
            limit_bytes: 1_000_000_000,
            used_bytes: 0,
            remaining_bytes: 1_000_000_000,
            reserved_bytes: 0,
            percentage: 0,
          },
          credits: { balance: 0 },
        });
      }
      if (path.endsWith('/subscription')) {
        return fulfillJson(route, {
          id: 'sub-1',
          status: 'active',
          plan: { id: 'plan-1', code: 'dev', name: 'Developer', status: 'active' },
          starts_at: '2026-01-01T00:00:00Z',
          current_period_start: '2026-08-01T00:00:00Z',
          current_period_end: '2026-09-01T00:00:00Z',
          ends_at: null,
        });
      }
      if (path.includes('/apps')) {
        return fulfillJson(route, { items: [], total: 0, limit: 50, offset: 0 });
      }
      if (path.includes('/billing') && session === 'agent' && !supportPerms.includes('billing.view')) {
        return fulfillJson(route, { code: 'insufficient_workspace_role' }, 403);
      }
      if (path.includes('/billing')) {
        return fulfillJson(route, { items: [], plans: [], subscription: null });
      }
      return fulfillJson(route, {});
    });
  }

  const ownerContext = await browser.newContext();
  const ownerPage = await ownerContext.newPage();
  session = 'owner';
  await mockApi(ownerPage);
  await ownerPage.goto('/members');
  await expect(ownerPage.getByTestId('members-page')).toBeVisible({ timeout: 15_000 });
  await ownerPage.getByTestId('roles-tab').click();
  await ownerPage.getByTestId('create-role-button').click();
  await ownerPage.getByTestId('role-name').fill('Support Agent');
  await ownerPage.getByTestId('permission-workspace.view').click();
  await ownerPage.getByTestId('permission-chat.use').click();
  await ownerPage.getByTestId('permission-experts.view').click();
  await ownerPage.getByTestId('role-save').click();
  await expect(ownerPage.getByTestId('roles-panel')).toContainText('Support Agent');

  await ownerPage.getByRole('tab', { name: 'Members' }).click();
  await ownerPage.getByTestId('invite-member-button').click();
  await ownerPage.getByTestId('invite-email').fill(agent.email);
  await ownerPage.getByTestId('invite-role-role-support').check();
  await ownerPage.getByTestId('invite-submit').click();
  await expect(ownerPage.getByTestId('pending-invitations')).toContainText(agent.email);

  const agentContext = await browser.newContext();
  const agentPage = await agentContext.newPage();
  session = 'guest';
  await mockApi(agentPage);
  await agentPage.goto(`/invitations/accept?token=${inviteToken}`);
  await expect(agentPage.getByTestId('invitation-accept-guest')).toBeVisible({
    timeout: 15_000,
  });
  await agentPage.getByTestId('invitation-login').click();
  await expect(agentPage.locator('#email')).toBeVisible({ timeout: 15_000 });
  await agentPage.locator('#email').fill(agent.email);
  await agentPage.locator('#password').fill('password12');
  await agentPage.getByRole('button', { name: 'Sign in' }).click();
  await expect(agentPage).toHaveURL(/\/(chat|overview)/, { timeout: 15_000 });
  await agentPage.goto('/overview');
  await expect(agentPage.getByTestId('workspace-nav')).toBeVisible({
    timeout: 15_000,
  });
  await expect(agentPage.getByTestId('nav-item-overview')).toBeVisible();
  await expect(agentPage.getByTestId('nav-item-chat')).toBeVisible();
  await expect(agentPage.getByTestId('nav-item-experts')).toBeVisible();
  await expect(agentPage.getByTestId('nav-item-apps')).toHaveCount(0);
  await expect(agentPage.getByTestId('nav-item-members')).toHaveCount(0);
  await expect(agentPage.getByTestId('nav-item-storage')).toHaveCount(0);
  await expect(agentPage.getByTestId('nav-group-billing')).toHaveCount(0);
  await expect(agentPage.getByTestId('nav-group-api')).toHaveCount(0);

  await agentPage.goto('/billing/subscription');
  await expect(agentPage.getByTestId('forbidden-page')).toBeVisible();
  await agentPage.goto('/experts');
  await expect(agentPage.getByTestId('forbidden-page')).toHaveCount(0);

  session = 'owner';
  await ownerPage.getByTestId('roles-tab').click();
  await ownerPage.getByTestId('edit-role-role-support').click();
  await ownerPage.getByTestId('permission-billing.view').click();
  await ownerPage.getByTestId('role-save').click();

  session = 'agent';
  await agentPage.reload();
  await expect(agentPage.getByTestId('nav-group-billing')).toBeVisible({ timeout: 15_000 });
  await agentPage.goto('/billing/subscription');
  await expect(agentPage.getByTestId('forbidden-page')).toHaveCount(0);

  await ownerContext.close();
  await agentContext.close();
});
