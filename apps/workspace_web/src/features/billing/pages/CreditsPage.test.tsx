import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { CreditPack } from '@/services/api/billing';
import type { Meter, UsageSummary } from '@/services/api/usage';
import { CreditsPage } from './CreditsPage';

const workspaceState = { id: 'ws-a' };

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: {
      id: workspaceState.id,
      name: 'Acme',
      slug: 'acme',
      role: 'owner',
    },
    currentMembership: {
      id: 'm1',
      workspace_id: workspaceState.id,
      user_id: 'u1',
      role: 'owner',
      created_at: '2026-01-01T00:00:00Z',
    },
  }),
}));

const getUsageSummary = vi.fn();
const getSubscription = vi.fn();
const listCreditPacks = vi.fn();
const createCreditPackCheckout = vi.fn();
const redirectToCheckout = vi.fn();

vi.mock('@/services/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/usage')>(
    '@/services/api/usage',
  );
  return {
    ...actual,
    getUsageSummary: () => getUsageSummary(),
    getSubscription: () => getSubscription(),
  };
});

vi.mock('@/services/api/billing', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/billing')>(
    '@/services/api/billing',
  );
  return {
    ...actual,
    listCreditPacks: () => listCreditPacks(),
    createCreditPackCheckout: (packId: string) => createCreditPackCheckout(packId),
  };
});

vi.mock('@/features/billing/lib/redirect', () => ({
  redirectToCheckout: (url: string) => redirectToCheckout(url),
}));

function meter(): Meter {
  return {
    limit: 1000,
    used: 10,
    reserved: 0,
    remaining: 990,
    period_start: null,
    period_end: null,
  };
}

function summary(balance = 250): UsageSummary {
  const m = meter();
  return {
    ai_tokens: { daily: m, weekly: m, monthly: m },
    ai: { daily: m, weekly: m, monthly: m },
    experts: m,
    storage_bytes: m,
    storage: {
      limit_bytes: 1000,
      used_bytes: 10,
      remaining_bytes: 990,
      reserved_bytes: 0,
      percentage: 1,
    },
    credits: { balance },
  };
}

const pack: CreditPack = {
  id: 'pack-1',
  code: 'starter',
  name: 'Starter pack',
  description: 'Extra tokens',
  credits: 4000,
  price_amount: '25.00',
  currency: 'SAR',
  active: true,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <CreditsPage />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

describe('CreditsPage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    getUsageSummary.mockReset();
    listCreditPacks.mockReset();
    createCreditPackCheckout.mockReset();
    redirectToCheckout.mockReset();
    getUsageSummary.mockResolvedValue(summary(250));
    listCreditPacks.mockResolvedValue([pack]);
    createCreditPackCheckout.mockResolvedValue({
      purchase_id: 'pur-c',
      status: 'redirected',
      kind: 'credit_pack',
      amount: '25.00',
      currency: 'SAR',
      redirect_url: 'https://pay.example/credits',
    });
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('renders purchased-credit balance and active packs', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-credits-balance')).toHaveTextContent('250');
    });
    expect(screen.getByText('Starter pack')).toBeInTheDocument();
    expect(screen.getByLabelText('SAR 25.00')).toBeInTheDocument();
  });

  it('creates checkout with the pack id only and redirects', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-pack-cta')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('billing-pack-cta'));
    fireEvent.click(await screen.findByTestId('billing-checkout-confirm'));
    await waitFor(() => {
      expect(createCreditPackCheckout).toHaveBeenCalledWith('pack-1');
    });
    expect(JSON.stringify(createCreditPackCheckout.mock.calls[0])).not.toContain('4000');
    expect(JSON.stringify(createCreditPackCheckout.mock.calls[0])).not.toContain('25.00');
    expect(JSON.stringify(createCreditPackCheckout.mock.calls[0])).not.toContain('clickpay');
    await waitFor(() => {
      expect(redirectToCheckout).toHaveBeenCalledWith('https://pay.example/credits');
    });
  });
});
