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

test('admin login → overview → placeholder → logout', async ({ page }) => {
  let loggedIn = false;
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path.endsWith('/auth/refresh') && method === 'POST') {
      if (!loggedIn) {
        return fulfillJson(route, { code: 'unauthorized' }, 401);
      }
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
    return fulfillJson(route, { code: 'not_found' }, 404);
  });

  await page.goto('/login');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await page.locator('#email').fill('admin@example.com');
  await page.locator('#password').fill('password123');
  await page.getByTestId('login-submit').click();
  await expect(page.getByTestId('overview-page')).toBeVisible();

  await page.getByTestId('nav-workspaces').click();
  await expect(page.getByTestId('coming-soon-page')).toBeVisible();

  await page.getByTestId('account-menu-trigger').first().click();
  await page.getByTestId('logout-menu-item').click();
  await page.getByTestId('logout-confirm').click();
  await expect(page.getByTestId('login-form')).toBeVisible();
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
