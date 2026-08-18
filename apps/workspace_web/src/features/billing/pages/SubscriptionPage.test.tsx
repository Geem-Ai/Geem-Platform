import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import { ApiError } from '@/services/api/errors';
import type { PurchasablePlan } from '@/services/api/billing';
import type { Entitlements, Subscription } from '@/services/api/usage';
import { WorkspacePermission } from '@/features/authz/permissions';
import { SubscriptionPage } from './SubscriptionPage';

const workspaceState: {
  id: string;
  role: string;
  permissions?: string[];
} = { id: 'ws-a', role: 'owner' };

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: workspaceState.id,
      name: 'Acme',
      slug: 'acme',
      role: workspaceState.role,
      permissions: workspaceState.permissions,
    },
    currentMembership: {
      id: 'm1',
      workspace_id: workspaceState.id,
      user_id: 'u1',
      role: workspaceState.role,
      created_at: '2026-01-01T00:00:00Z',
      permissions: workspaceState.permissions,
    },
  }),
}));

const getSubscription = vi.fn();
const getEntitlements = vi.fn();
const listBillingPlans = vi.fn();
const createSubscriptionCheckout = vi.fn();
const redirectToCheckout = vi.fn();

vi.mock('@/services/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/usage')>(
    '@/services/api/usage',
  );
  return {
    ...actual,
    getSubscription: () => getSubscription(),
    getEntitlements: () => getEntitlements(),
  };
});

vi.mock('@/services/api/billing', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/billing')>(
    '@/services/api/billing',
  );
  return {
    ...actual,
    listBillingPlans: () => listBillingPlans(),
    createSubscriptionCheckout: (planId: string) => createSubscriptionCheckout(planId),
  };
});

vi.mock('@/features/billing/lib/redirect', () => ({
  redirectToCheckout: (url: string) => redirectToCheckout(url),
}));

const currentPlan: PurchasablePlan = {
  id: 'plan-dev',
  code: 'bootstrap_dev',
  name: 'Developer',
  description: 'Current workspace plan',
  status: 'active',
  price_amount: '49.00',
  currency: 'SAR',
  entitlements: [
    { key: 'ai_tokens_monthly', value: 30000, value_type: 'integer' },
    { key: 'storage_bytes', value: 1_000_000, value_type: 'integer' },
    { key: 'ai_tokens_daily', value: 1000, value_type: 'integer' },
    { key: 'experts_limit', value: 5, value_type: 'integer' },
    { key: 'ai_tokens_weekly', value: 7000, value_type: 'integer' },
  ],
};

const proPlan: PurchasablePlan = {
  id: 'plan-pro',
  code: 'pro',
  name: 'Growth',
  description: 'More capacity',
  status: 'active',
  price_amount: '99.00',
  currency: 'SAR',
  entitlements: [
    { key: 'ai_tokens_monthly', value: 150000, value_type: 'integer' },
    { key: 'ai_tokens_daily', value: 5000, value_type: 'integer' },
    { key: 'ai_tokens_weekly', value: 35000, value_type: 'integer' },
    { key: 'experts_limit', value: 20, value_type: 'integer' },
  ],
};

const subscription: Subscription = {
  id: 'sub-a',
  status: 'active',
  plan: { id: 'plan-dev', code: 'bootstrap_dev', name: 'Developer', status: 'active' },
  starts_at: '2026-01-01T00:00:00Z',
  current_period_start: '2026-08-01T00:00:00Z',
  current_period_end: '2026-09-01T00:00:00Z',
  ends_at: null,
};

const entitlements: Entitlements = {
  subscription_id: 'sub-a',
  plan: subscription.plan,
  items: currentPlan.entitlements,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <SubscriptionPage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('SubscriptionPage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    workspaceState.role = 'owner';
    workspaceState.permissions = undefined;
    getSubscription.mockReset();
    getEntitlements.mockReset();
    listBillingPlans.mockReset();
    createSubscriptionCheckout.mockReset();
    redirectToCheckout.mockReset();
    getSubscription.mockResolvedValue(subscription);
    getEntitlements.mockResolvedValue(entitlements);
    listBillingPlans.mockResolvedValue([currentPlan, proPlan]);
    createSubscriptionCheckout.mockResolvedValue({
      purchase_id: 'pur-1',
      status: 'redirected',
      kind: 'subscription',
      amount: '99.00',
      currency: 'SAR',
      redirect_url: 'https://pay.example/hosted',
    });
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('renders the current plan and available plans', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-current-plan-name')).toHaveTextContent('Developer');
    });
    expect(screen.getByTestId('billing-plan-plan-dev')).toHaveAttribute('data-current', 'true');
    expect(screen.getByTestId('billing-plan-current')).toHaveTextContent('Current');
    expect(
      screen.getByTestId('billing-current-plan-price').querySelector('[aria-label="SAR 49.00"]'),
    ).toBeTruthy();
    expect(screen.getByText('Growth')).toBeInTheDocument();
    expect(screen.getByLabelText('SAR 99.00')).toBeInTheDocument();
  });

  it('renders allowance cards daily then weekly then monthly', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-entitlement-summary')).toBeInTheDocument();
    });
    const summaryKeys = [
      ...screen
        .getByTestId('billing-entitlement-summary')
        .querySelectorAll('[data-entitlement-key]'),
    ].map((node) => node.getAttribute('data-entitlement-key'));
    expect(summaryKeys.slice(0, 3)).toEqual([
      'ai_tokens_daily',
      'ai_tokens_weekly',
      'ai_tokens_monthly',
    ]);
    const planKeys = [
      ...screen
        .getByTestId('billing-plan-entitlements-plan-pro')
        .querySelectorAll('[data-entitlement-key]'),
    ].map((node) => node.getAttribute('data-entitlement-key'));
    expect(planKeys.slice(0, 3)).toEqual([
      'ai_tokens_daily',
      'ai_tokens_weekly',
      'ai_tokens_monthly',
    ]);
  });

  it('creates checkout with the plan id only and redirects using redirect_url', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Growth')).toBeInTheDocument();
    });
    const proCard = screen.getByTestId('billing-plan-plan-pro');
    fireEvent.click(proCard.querySelector('[data-testid="billing-plan-cta"]')!);
    await waitFor(() => {
      expect(screen.getByTestId('billing-checkout-dialog')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('billing-checkout-confirm'));
    await waitFor(() => {
      expect(createSubscriptionCheckout).toHaveBeenCalledWith('plan-pro');
    });
    expect(createSubscriptionCheckout.mock.calls[0]).toEqual(['plan-pro']);
    expect(JSON.stringify(createSubscriptionCheckout.mock.calls[0])).not.toContain('99.00');
    expect(JSON.stringify(createSubscriptionCheckout.mock.calls[0])).not.toContain('clickpay');
    await waitFor(() => {
      expect(redirectToCheckout).toHaveBeenCalledWith('https://pay.example/hosted');
    });
  });

  it('shows a typed checkout error', async () => {
    createSubscriptionCheckout.mockRejectedValue(
      new ApiError('down', { status: 503, code: 'billing_gateway_unavailable' }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Growth')).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByTestId('billing-plan-plan-pro').querySelector('[data-testid="billing-plan-cta"]')!,
    );
    fireEvent.click(await screen.findByTestId('billing-checkout-confirm'));
    await waitFor(() => {
      expect(screen.getByTestId('billing-checkout-error')).toHaveTextContent(
        'Checkout is temporarily unavailable',
      );
    });
    expect(redirectToCheckout).not.toHaveBeenCalled();
  });

  it('keeps checkout CTAs for members who can manage billing', async () => {
    workspaceState.role = 'member';
    workspaceState.permissions = [
      WorkspacePermission.BILLING_VIEW,
      WorkspacePermission.BILLING_MANAGE,
    ];
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Growth')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('billing-plan-plan-pro').querySelector('[data-testid="billing-plan-cta"]'),
    ).toBeEnabled();
  });

  it('hides checkout CTAs without billing.manage', async () => {
    workspaceState.role = 'member';
    workspaceState.permissions = [WorkspacePermission.BILLING_VIEW];
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Growth')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('billing-plan-plan-pro').querySelector('[data-testid="billing-plan-cta"]'),
    ).toBeNull();
  });

  it('scopes plan query keys to the workspace', async () => {
    const { client } = renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-current-plan-name')).toBeInTheDocument();
    });
    expect(queryKeys.billingPlans('ws-a')).toEqual(['workspace', 'ws-a', 'billing', 'plans']);
    expect(client.getQueryData(queryKeys.billingPlans('ws-a'))).toBeTruthy();
    expect(queryKeys.billingPlans('ws-a')).not.toEqual(queryKeys.billingPlans('ws-b'));
  });

  it('renders Arabic copy', async () => {
    await i18n.changeLanguage('ar');
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'الاشتراك' })).toBeInTheDocument();
    });
    expect(document.documentElement.dir).toBe('rtl');
  });
});
