import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { Purchase, PurchaseList } from '@/services/api/billing';
import { BillingHistoryPage } from './BillingHistoryPage';

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

vi.mock('@/lib/download', () => ({
  triggerBrowserDownload: vi.fn(),
}));

const listPurchases = vi.fn();
const downloadPurchaseInvoice = vi.fn();

vi.mock('@/services/api/billing', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/billing')>(
    '@/services/api/billing',
  );
  return {
    ...actual,
    listPurchases: (params?: unknown) => listPurchases(params),
    downloadPurchaseInvoice: (id: string) => downloadPurchaseInvoice(id),
  };
});

function purchase(overrides: Partial<Purchase> = {}): Purchase {
  return {
    id: 'pur-1',
    status: 'paid',
    kind: 'credit_pack',
    amount: '25.00',
    currency: 'SAR',
    item_name: 'Starter pack',
    item_code: 'starter',
    credits: 4000,
    paid_at: '2026-08-13T12:00:00Z',
    created_at: '2026-08-13T11:00:00Z',
    ...overrides,
  };
}

function list(items: Purchase[], total = items.length): PurchaseList {
  return { items, total, limit: 25, offset: 0 };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <BillingHistoryPage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('BillingHistoryPage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    listPurchases.mockReset();
    downloadPurchaseInvoice.mockReset();
    listPurchases.mockResolvedValue(list([purchase()]));
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('renders purchase rows with localized status badges', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-history-list')).toBeInTheDocument();
    });
    expect(screen.getByText('Starter pack')).toBeInTheDocument();
    expect(screen.getByTestId('billing-history-row')).toHaveTextContent('Paid');
    expect(screen.getByLabelText('SAR 25.00')).toBeInTheDocument();
    expect(screen.queryByText('tran_ref')).not.toBeInTheDocument();
    expect(screen.queryByText('server_key')).not.toBeInTheDocument();
  });

  it('shows an invoice download on paid rows only', async () => {
    listPurchases.mockResolvedValue(
      list([
        purchase({ id: 'paid-1', status: 'paid' }),
        purchase({ id: 'pend-1', status: 'pending', item_name: 'Pending pack' }),
      ]),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-invoice-download-paid-1')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('billing-invoice-download-pend-1')).not.toBeInTheDocument();
  });

  it('downloads the invoice PDF for a paid purchase', async () => {
    const { triggerBrowserDownload } = await import('@/lib/download');
    downloadPurchaseInvoice.mockResolvedValue({
      blob: new Blob(['%PDF'], { type: 'application/pdf' }),
      filename: 'GEEM-000001.pdf',
      contentType: 'application/pdf',
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-invoice-download-pur-1')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('billing-invoice-download-pur-1'));
    await waitFor(() => {
      expect(downloadPurchaseInvoice).toHaveBeenCalledWith('pur-1');
    });
    expect(triggerBrowserDownload).toHaveBeenCalled();
  });

  it('shows an empty state', async () => {
    listPurchases.mockResolvedValue(list([]));
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-history-empty')).toBeInTheDocument();
    });
  });

  it('shows a loading state', () => {
    listPurchases.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByTestId('billing-history-loading')).toBeInTheDocument();
  });

  it('shows an error state', async () => {
    listPurchases.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('billing-history-error')).toBeInTheDocument();
    });
  });

  it('does not reuse purchase cache across workspaces', async () => {
    const { client, rerender } = renderPage();
    await waitFor(() => {
      expect(screen.getByText('Starter pack')).toBeInTheDocument();
    });
    expect(queryKeys.billingPurchases('ws-a', {
      limit: 25,
      offset: 0,
      status: undefined,
      kind: undefined,
    })).toEqual([
      'workspace',
      'ws-a',
      'billing',
      'purchases',
      { limit: 25, offset: 0, status: undefined, kind: undefined },
    ]);
    expect(client.getQueryData(queryKeys.billingPurchases('ws-b'))).toBeUndefined();

    workspaceState.id = 'ws-b';
    listPurchases.mockReturnValue(new Promise(() => undefined));
    rerender(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <BillingHistoryPage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    );
    expect(screen.queryByText('Starter pack')).not.toBeInTheDocument();
  });
});
