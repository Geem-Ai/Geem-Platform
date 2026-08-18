import { expect, test, type Page, type Route } from '@playwright/test';

const workspaceId = 'ws-e2e-10b';
const inviteToken = 'e2e-invite-token';
const resentToken = 'e2e-invite-token-rotated';

const owner = {
  id: 'user-owner',
  email: 'owner@example.com',
  status: 'active',
  platform_role: 'none',
  created_at: '2026-01-01T00:00:00Z',
};

const invitee = {
  id: 'user-invitee',
  email: 'alice@example.com',
  status: 'active',
  platform_role: 'none',
  created_at: '2026-01-02T00:00:00Z',
};

const bob = {
  id: 'user-bob',
  email: 'bob@example.com',
  status: 'active',
  platform_role: 'none',
  created_at: '2026-01-03T00:00:00Z',
};

type RoleSummary = {
  id: string;
  name: string;
  is_system: boolean;
  is_owner_role: boolean;
  system_key: string | null;
};

const ownerRole: RoleSummary = {
  id: 'role-owner',
  name: 'Owner',
  is_system: true,
  is_owner_role: true,
  system_key: 'owner',
};
const adminRole: RoleSummary = {
  id: 'role-admin',
  name: 'Administrator',
  is_system: true,
  is_owner_role: false,
  system_key: 'admin',
};
const memberRole: RoleSummary = {
  id: 'role-member',
  name: 'Member',
  is_system: true,
  is_owner_role: false,
  system_key: 'member',
};

const OWNER_PERMISSIONS = ['workspace.view', 'chat.use', 'experts.view', 'members.view', 'members.invite', 'members.update_role', 'members.remove', 'roles.view', 'roles.manage', 'billing.view'];
const MEMBER_PERMISSIONS = ['workspace.view', 'chat.use', 'experts.view', 'members.view', 'billing.view', 'apps.view', 'storage.view'];

type MemberRow = {
  id: string;
  user_id: string;
  email: string;
  role: RoleSummary;
  created_at: string;
};

type InviteRow = {
  id: string;
  workspace_id: string;
  email: string;
  role: RoleSummary;
  status: string;
  expires_at: string;
  created_at: string;
  invited_by: { id: string; email: string };
};

function workspace(role: RoleSummary, permissions: string[]) {
  return {
    id: workspaceId,
    name: 'E2E Workspace',
    slug: 'e2e',
    status: 'active',
    role,
    permissions,
    kind: 'tenant',
  };
}

function tokenResponse(user: typeof owner) {
  return {
    access_token: `e2e-${user.id}`,
    token_type: 'bearer',
    expires_at: '2027-01-01T00:00:00Z',
    user,
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function createStore() {
  const members: MemberRow[] = [
    {
      id: 'mem-owner',
      user_id: owner.id,
      email: owner.email,
      role: ownerRole,
      created_at: '2026-01-01T00:00:00Z',
    },
  ];
  const invitations: InviteRow[] = [];
  let currentToken = inviteToken;
  let revoked = false;
  return {
    members,
    invitations,
    get currentToken() {
      return currentToken;
    },
    rotateToken() {
      currentToken = resentToken;
    },
    revoke() {
      revoked = true;
      invitations.splice(0, invitations.length);
    },
    get revoked() {
      return revoked;
    },
  };
}

type Session = 'owner' | 'member' | 'invitee' | 'bob' | 'guest';

async function mockApi(
  page: Page,
  store: ReturnType<typeof createStore>,
  sessionRef: { current: Session },
) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const session = sessionRef.current;
    const actor =
      session === 'owner'
        ? owner
        : session === 'invitee'
          ? invitee
          : session === 'bob'
            ? bob
            : session === 'member'
              ? {
                  id: 'user-member',
                  email: 'member@example.com',
                  status: 'active',
                  platform_role: 'none',
                  created_at: '2026-01-01T00:00:00Z',
                }
              : null;
    const role = session === 'member' ? memberRole : ownerRole;
    const permissions =
      session === 'member' ? MEMBER_PERMISSIONS : OWNER_PERMISSIONS;
    const ws = workspace(role, permissions);
    const joined = store.members.some((m) => m.user_id === actor?.id);
    const meWorkspaces = actor && (session === 'invitee' ? joined : session !== 'bob')
      ? [session === 'invitee' ? workspace(memberRole, MEMBER_PERMISSIONS) : ws]
      : [];

    if (path.endsWith('/auth/refresh') && method === 'POST') {
      if (!actor) {
        return fulfillJson(route, { code: 'unauthorized' }, 401);
      }
      return fulfillJson(route, tokenResponse(actor));
    }
    if ((path.endsWith('/auth/login') || path.endsWith('/auth/register')) && method === 'POST') {
      const body = route.request().postDataJSON() as { email?: string };
      if (body.email === invitee.email) {
        sessionRef.current = 'invitee';
        return fulfillJson(route, tokenResponse(invitee));
      }
      if (body.email === bob.email) {
        sessionRef.current = 'bob';
        return fulfillJson(route, tokenResponse(bob));
      }
      sessionRef.current = 'owner';
      return fulfillJson(route, tokenResponse(owner));
    }
    if (path.endsWith('/auth/logout') && method === 'POST') {
      sessionRef.current = 'guest';
      return fulfillJson(route, {});
    }
    if (path.endsWith('/auth/me') && method === 'GET') {
      if (!actor) return fulfillJson(route, { code: 'unauthorized' }, 401);
      const current = meWorkspaces[0] ?? null;
      return fulfillJson(route, {
        user: actor,
        workspaces: meWorkspaces,
        current_workspace: current,
        membership: current
          ? {
              id: `mem-${actor.id}`,
              workspace_id: current.id,
              user_id: actor.id,
              role: current.role,
              created_at: '2026-01-01T00:00:00Z',
              permissions: current.permissions,
            }
          : null,
      });
    }
    if (path.endsWith('/workspaces') && method === 'GET') {
      return fulfillJson(route, meWorkspaces);
    }
    if (path.includes(`/workspaces/${workspaceId}/roles/assignable`) && method === 'GET') {
      return fulfillJson(route, { items: [adminRole, memberRole] });
    }
    if (path.includes(`/workspaces/${workspaceId}/roles`) && method === 'GET') {
      return fulfillJson(route, {
        items: [
          { ...ownerRole, workspace_id: workspaceId, description: null, assigned_count: 1, permissions: [] },
          { ...adminRole, workspace_id: workspaceId, description: null, assigned_count: 0, permissions: [] },
          { ...memberRole, workspace_id: workspaceId, description: null, assigned_count: 0, permissions: [] },
        ],
      });
    }
    if (path.includes(`/workspaces/${workspaceId}/permissions`) && method === 'GET') {
      return fulfillJson(route, { items: [] });
    }
    if (path.includes(`/workspaces/${workspaceId}/members`) && method === 'GET') {
      return fulfillJson(route, store.members);
    }
    if (
      path.includes(`/workspaces/${workspaceId}/invitations`) &&
      path.endsWith('/resend') &&
      method === 'POST'
    ) {
      store.rotateToken();
      const item = store.invitations[0];
      if (!item) return fulfillJson(route, { code: 'invitation_not_found' }, 404);
      item.expires_at = '2026-08-25T12:00:00Z';
      return fulfillJson(route, item);
    }
    if (
      /\/workspaces\/[^/]+\/invitations\/[^/]+$/.test(path) &&
      method === 'DELETE'
    ) {
      store.revoke();
      return route.fulfill({ status: 204, body: '' });
    }
    if (path.includes(`/workspaces/${workspaceId}/invitations`) && method === 'POST') {
      const body = route.request().postDataJSON() as {
        email?: string;
        role_id?: string;
      };
      if (store.members.some((m) => m.email === body.email)) {
        return fulfillJson(route, { code: 'already_workspace_member' }, 409);
      }
      if (store.invitations.some((i) => i.email === body.email)) {
        return fulfillJson(route, { code: 'invitation_already_exists' }, 409);
      }
      const invitedRole =
        body.role_id === adminRole.id ? adminRole : memberRole;
      const item: InviteRow = {
        id: 'inv-1',
        workspace_id: workspaceId,
        email: (body.email ?? '').toLowerCase(),
        role: invitedRole,
        status: 'pending',
        expires_at: '2026-08-21T12:00:00Z',
        created_at: '2026-08-18T12:00:00Z',
        invited_by: { id: owner.id, email: owner.email },
      };
      store.invitations.push(item);
      return fulfillJson(route, item, 201);
    }
    if (path.includes(`/workspaces/${workspaceId}/invitations`) && method === 'GET') {
      return fulfillJson(route, {
        items: store.invitations,
        total: store.invitations.length,
        limit: 50,
        offset: 0,
      });
    }
    if (path.endsWith('/invitations/accept') && method === 'POST') {
      const body = route.request().postDataJSON() as { token?: string };
      if (store.revoked) {
        return fulfillJson(route, { code: 'invitation_revoked' }, 409);
      }
      if (body.token !== store.currentToken) {
        return fulfillJson(route, { code: 'invalid_invitation' }, 400);
      }
      if (session === 'bob') {
        return fulfillJson(route, { code: 'invitation_email_mismatch' }, 403);
      }
      const already = store.members.some((m) => m.user_id === invitee.id);
      if (!already) {
        store.members.push({
          id: 'mem-invitee',
          user_id: invitee.id,
          email: invitee.email,
          role: memberRole,
          created_at: '2026-08-18T12:00:00Z',
        });
        store.invitations.splice(0, store.invitations.length);
      }
      return fulfillJson(route, {
        invitation_id: 'inv-1',
        workspace_id: workspaceId,
        workspace_name: 'E2E Workspace',
        workspace_slug: 'e2e',
        role: memberRole,
        membership_id: 'mem-invitee',
        already_member: already,
      });
    }

    return fulfillJson(route, {});
  });
}

test.describe('Members Phase 10B invitations', () => {
  test('owner invites, invitee accepts, member appears', async ({ browser }) => {
    const store = createStore();
    const ownerSession: { current: Session } = { current: 'owner' };
    const ownerContext = await browser.newContext();
    const ownerPage = await ownerContext.newPage();
    await mockApi(ownerPage, store, ownerSession);
    await ownerPage.goto('/members');
    await expect(ownerPage.getByTestId('members-page')).toBeVisible({ timeout: 15_000 });
    await ownerPage.getByTestId('invite-member-button').click();
    await ownerPage.getByTestId('invite-email').fill(invitee.email);
    await ownerPage.getByTestId('invite-role-member').check();
    await ownerPage.getByTestId('invite-submit').click();
    await expect(ownerPage.getByTestId('pending-invitations')).toContainText(invitee.email);

    const inviteeSession: { current: Session } = { current: 'guest' };
    const inviteeContext = await browser.newContext();
    const inviteePage = await inviteeContext.newPage();
    await mockApi(inviteePage, store, inviteeSession);
    await inviteePage.goto(`/invitations/accept?token=${inviteToken}`);
    await expect(inviteePage.getByTestId('invitation-accept-guest')).toBeVisible({
      timeout: 15_000,
    });
    await inviteePage.getByTestId('invitation-login').click();
    await inviteePage.locator('#email').fill(invitee.email);
    await inviteePage.locator('#password').fill('password12');
    await inviteePage.getByRole('button', { name: 'Sign in' }).click();
    await expect(inviteePage).not.toHaveURL(/token=/, { timeout: 15_000 });
    await inviteePage.goto('/members');
    await expect(inviteePage.getByTestId('members-page')).toContainText(invitee.email);
    expect(inviteePage.url()).not.toContain('token=');

    await ownerPage.reload();
    await expect(ownerPage.getByTestId('members-table')).toContainText(invitee.email);

    await ownerContext.close();
    await inviteeContext.close();
  });

  test('member cannot invite or manage invitations', async ({ page }) => {
    const store = createStore();
    const session: { current: Session } = { current: 'member' };
    store.members.push({
      id: 'mem-member',
      user_id: 'user-member',
      email: 'member@example.com',
      role: memberRole,
      created_at: '2026-01-04T00:00:00Z',
    });
    await mockApi(page, store, session);
    await page.goto('/members');
    await expect(page.getByTestId('members-page')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('invite-member-button')).toHaveCount(0);
    await expect(page.getByTestId('pending-invitations')).toHaveCount(0);
    await expect(page.getByTestId('roles-tab')).toHaveCount(0);
  });

  test('email mismatch blocks acceptance', async ({ page }) => {
    const store = createStore();
    store.invitations.push({
      id: 'inv-1',
      workspace_id: workspaceId,
      email: invitee.email,
      role: memberRole,
      status: 'pending',
      expires_at: '2026-08-21T12:00:00Z',
      created_at: '2026-08-18T12:00:00Z',
      invited_by: { id: owner.id, email: owner.email },
    });
    const session: { current: Session } = { current: 'bob' };
    await mockApi(page, store, session);
    await page.goto(`/invitations/accept?token=${inviteToken}`);
    await expect(page.getByTestId('invitation-mismatch')).toBeVisible({ timeout: 15_000 });
  });

  test('revoked invitation cannot be accepted', async ({ page }) => {
    const store = createStore();
    store.revoke();
    const session: { current: Session } = { current: 'invitee' };
    await mockApi(page, store, session);
    await page.goto(`/invitations/accept?token=${inviteToken}`);
    await expect(page.getByTestId('invitation-revoked')).toBeVisible({ timeout: 15_000 });
  });

  test('resend rotates the token used for acceptance', async ({ browser }) => {
    const store = createStore();
    const ownerSession: { current: Session } = { current: 'owner' };
    const ownerContext = await browser.newContext();
    const ownerPage = await ownerContext.newPage();
    store.invitations.push({
      id: 'inv-1',
      workspace_id: workspaceId,
      email: invitee.email,
      role: memberRole,
      status: 'pending',
      expires_at: '2026-08-21T12:00:00Z',
      created_at: '2026-08-18T12:00:00Z',
      invited_by: { id: owner.id, email: owner.email },
    });
    await mockApi(ownerPage, store, ownerSession);
    await ownerPage.goto('/members');
    await ownerPage.getByTestId('resend-invitation').click();
    await expect(ownerPage.getByTestId('pending-invitations')).toBeVisible();

    const staleSession: { current: Session } = { current: 'invitee' };
    const stalePage = await (await browser.newContext()).newPage();
    await mockApi(stalePage, store, staleSession);
    await stalePage.goto(`/invitations/accept?token=${inviteToken}`);
    await expect(stalePage.getByTestId('invitation-invalid')).toBeVisible({
      timeout: 15_000,
    });

    const freshPage = await (await browser.newContext()).newPage();
    await mockApi(freshPage, store, { current: 'invitee' });
    await freshPage.goto(`/invitations/accept?token=${resentToken}`);
    await expect(freshPage).not.toHaveURL(/token=/, { timeout: 15_000 });
    await freshPage.goto('/members');
    await expect(freshPage.getByTestId('members-page')).toBeVisible();

    await ownerContext.close();
  });

  test('Arabic RTL members page and invite dialog', async ({ page }) => {
    const store = createStore();
    await mockApi(page, store, { current: 'owner' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/members');
    await expect(page.getByTestId('members-page')).toBeVisible({ timeout: 15_000 });
    await page.getByTestId('account-menu-trigger').click();
    await page.getByTestId('language-menu').click();
    await page.getByTestId('language-option-ar').click();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('members-page')).toContainText('الأعضاء');
    await page.getByTestId('invite-member-button').click();
    await expect(page.getByTestId('invite-dialog')).toBeVisible();
    await expect(page.getByTestId('invite-dialog')).toContainText('دعوة عضو');
  });
});
