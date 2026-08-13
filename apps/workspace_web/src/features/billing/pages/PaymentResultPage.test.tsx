import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { Purchase } from '@/services/api/billing';
import { PaymentResultPage } from './PaymentResultPage';
import { PaymentOutcomeDialog } from '../components/PaymentOutcomeDialog';

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

const getPurchase = vi.fn();

vi.mock('@/services/api/billing', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/billing')>(
    '@/services/api/billing',
  );
  return {
    ...actual,
    getPurchase: (id: string) => getPurchase(id),
  };
});

function purchase(overrides: Partial<Purchase> = {}): Purchase {
  return {
    id: 'pur-1',
    status: 'paid',
    kind: 'subscription',
    amount: '99.00',
    currency: 'SAR',
    item_name: 'Growth',
    item_code: 'pro',
    credits: null,
    paid_at: '2026-08-13T12:00:00Z',
    created_at: '2026-08-13T11:00:00Z',
    ...overrides,
  };
}

function renderResult(search: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  return {
    client,
    invalidate,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={[`/billing/payment/failed${search}`]}>
            <Routes>
              <Route path="/billing/payment/failed" element={<PaymentResultPage />} />
              <Route path="/billing/payment/success" element={<PaymentResultPage />} />
              <Route
                path="/billing/subscription"
                element={
                  <div data-testid="subscription-dest">
                    <PaymentOutcomeDialog />
                  </div>
                }
              />
              <Route
                path="/billing/credits"
                element={
                  <div data-testid="credits-dest">
                    <PaymentOutcomeDialog />
                  </div>
                }
              />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('PaymentResultPage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    getPurchase.mockReset();
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('redirects a failed purchase to subscription with an outcome dialog', async () => {
    getPurchase.mockResolvedValue(purchase({ status: 'failed', paid_at: null }));
    renderResult('?purchase=pur-1');
    await waitFor(() => {
      expect(screen.getByTestId('subscription-dest')).toBeInTheDocument();
    });
    expect(screen.getByTestId('billing-payment-outcome-dialog')).toHaveAttribute(
      'data-notice',
      'failed',
    );
    expect(screen.getByText('Payment not completed')).toBeInTheDocument();
    expect(getPurchase).toHaveBeenCalledWith('pur-1');
  });

  it('redirects a paid subscription to subscription with a success dialog', async () => {
    getPurchase.mockResolvedValue(purchase());
    renderResult('?purchase=pur-1');
    await waitFor(() => {
      expect(screen.getByTestId('subscription-dest')).toBeInTheDocument();
    });
    expect(screen.getByTestId('billing-payment-outcome-dialog')).toHaveAttribute(
      'data-notice',
      'success',
    );
    expect(screen.getByText('Payment successful')).toBeInTheDocument();
  });

  it('redirects a paid credit pack to credits', async () => {
    getPurchase.mockResolvedValue(
      purchase({ kind: 'credit_pack', item_name: 'Starter pack' }),
    );
    renderResult('?purchase=pur-1');
    await waitFor(() => {
      expect(screen.getByTestId('credits-dest')).toBeInTheDocument();
    });
    expect(screen.getByTestId('billing-payment-outcome-dialog')).toHaveAttribute(
      'data-notice',
      'success',
    );
  });

  it('does not treat provider query params as the purchase id', async () => {
    getPurchase.mockResolvedValue(purchase({ status: 'failed', paid_at: null }));
    renderResult('?purchase=pur-1&respStatus=A&tranRef=secret');
    await waitFor(() => {
      expect(screen.getByTestId('subscription-dest')).toBeInTheDocument();
    });
    expect(getPurchase).toHaveBeenCalledWith('pur-1');
    expect(getPurchase).not.toHaveBeenCalledWith(expect.stringContaining('respStatus'));
  });

  it('invalidates workspace-scoped billing caches after a paid result', async () => {
    getPurchase.mockResolvedValue(purchase());
    const { invalidate } = renderResult('?purchase=pur-1');
    await waitFor(() => {
      expect(invalidate).toHaveBeenCalled();
    });
    const keys = invalidate.mock.calls.map((call) => call[0]?.queryKey);
    expect(keys).toContainEqual(queryKeys.subscription('ws-a'));
    expect(keys).toContainEqual(queryKeys.usageSummary('ws-a'));
    expect(keys).toContainEqual(queryKeys.billingPurchases('ws-a'));
    expect(keys.some((key) => Array.isArray(key) && key[1] === 'ws-b')).toBe(false);
  });
});
