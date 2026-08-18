import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { queryKeys } from '@/services/api/query-keys';
import type { DocumentListPage, DocumentSummary } from '@/services/api/types';
import type { Meter, UsageSummary } from '@/services/api/usage';
import { WorkspacePermission } from '@/features/authz/permissions';
import { StoragePage } from './StoragePage';

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

vi.mock('@/lib/download', () => ({
  triggerBrowserDownload: vi.fn(),
}));

const listDocuments = vi.fn();
const deleteDocument = vi.fn();
const downloadDocumentFile = vi.fn();

vi.mock('@/services/api/documents', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/documents')>(
    '@/services/api/documents',
  );
  return {
    ...actual,
    listDocuments: (params: unknown) => listDocuments(params),
    deleteDocument: (id: string) => deleteDocument(id),
    downloadDocumentFile: (id: string) => downloadDocumentFile(id),
  };
});

const getUsageSummary = vi.fn();

vi.mock('@/services/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/usage')>(
    '@/services/api/usage',
  );
  return {
    ...actual,
    getUsageSummary: () => getUsageSummary(),
  };
});

function meter(partial: Partial<Meter> = {}): Meter {
  return {
    limit: 10485760,
    used: 1048576,
    reserved: 0,
    remaining: 9437184,
    period_start: null,
    period_end: null,
    ...partial,
  };
}

function usage(): UsageSummary {
  const storageBytes = meter();
  return {
    ai_tokens: { daily: meter(), weekly: meter(), monthly: meter() },
    ai: { daily: meter(), weekly: meter(), monthly: meter() },
    experts: meter({ used: 1, limit: 5, remaining: 4 }),
    storage_bytes: storageBytes,
    storage: {
      limit_bytes: 10485760,
      used_bytes: 1048576,
      remaining_bytes: 9437184,
      reserved_bytes: 0,
      percentage: 10,
    },
    credits: { balance: 0 },
  };
}

function file(partial: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: 'doc-1',
    title: 'Policy',
    original_filename: 'policy.pdf',
    status: 'ready',
    page_count: 2,
    byte_size: 2048,
    mime_type: 'application/pdf',
    processed_pages: 2,
    failed_pages: 0,
    current_stage: null,
    progress: 1,
    failure_reason: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    completed_at: '2026-08-01T00:00:00Z',
    experts: [{ id: 'ex-1', name: 'Legal' }],
    ...partial,
  };
}

function page(partial: Partial<DocumentListPage> = {}): DocumentListPage {
  return {
    items: [file()],
    total: 1,
    limit: 25,
    offset: 0,
    ...partial,
  };
}

function renderPage(initial = '/storage') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={[initial]}>
            <StoragePage />
          </MemoryRouter>
        </I18nextProvider>
      </QueryClientProvider>,
    ),
  };
}

describe('StoragePage', () => {
  beforeEach(async () => {
    workspaceState.id = 'ws-a';
    workspaceState.role = 'owner';
    workspaceState.permissions = undefined;
    listDocuments.mockReset();
    deleteDocument.mockReset();
    downloadDocumentFile.mockReset();
    getUsageSummary.mockReset();
    listDocuments.mockResolvedValue(page());
    getUsageSummary.mockResolvedValue(usage());
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('renders meter, file row, expert link, and download', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('storage-file-list')).toBeInTheDocument();
    });
    expect(screen.getByTestId('storage-quota-meter')).toBeInTheDocument();
    expect(screen.getByText('Policy')).toBeInTheDocument();
    expect(screen.getByText('Legal')).toBeInTheDocument();
    expect(screen.getByTestId('storage-download-doc-1')).toBeInTheDocument();
    expect(screen.getByTestId('storage-delete-doc-1')).toBeInTheDocument();
    expect(screen.getByTestId('storage-usage-link')).toHaveAttribute('href', '/billing/usage');
    expect(screen.getByTestId('storage-experts-link')).toHaveAttribute('href', '/experts');
    expect(screen.getByText(i18n.t('storage.filesTitle'))).toBeInTheDocument();
  });

  it('shows orphan badge when a file has no experts', async () => {
    listDocuments.mockResolvedValue(page({ items: [file({ experts: [] })] }));
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('storage-orphan-doc-1')).toBeInTheDocument();
    });
    expect(screen.getByText(i18n.t('storage.orphan'))).toBeInTheDocument();
  });

  it('hides delete for members who can still download', async () => {
    workspaceState.role = 'member';
    workspaceState.permissions = [
      WorkspacePermission.STORAGE_VIEW,
      WorkspacePermission.STORAGE_DOWNLOAD,
    ];
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('storage-download-doc-1')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('storage-delete-doc-1')).not.toBeInTheDocument();
  });

  it('hides download without storage.download', async () => {
    workspaceState.role = 'member';
    workspaceState.permissions = [WorkspacePermission.STORAGE_VIEW];
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Policy')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('storage-download-doc-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('storage-delete-doc-1')).not.toBeInTheDocument();
  });

  it('confirms delete and invalidates workspace caches', async () => {
    deleteDocument.mockResolvedValue({ status: 'deleted', id: 'doc-1' });
    const { client } = renderPage();
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    await waitFor(() => {
      expect(screen.getByTestId('storage-delete-doc-1')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('storage-delete-doc-1'));
    fireEvent.click(screen.getByTestId('storage-delete-confirm'));
    await waitFor(() => {
      expect(deleteDocument).toHaveBeenCalledWith('doc-1');
    });
    expect(invalidate).toHaveBeenCalled();
    expect(client.getQueryCache().findAll({ queryKey: queryKeys.documents('ws-a') }).length).toBeGreaterThan(0);
  });

  it('renders Arabic copy', async () => {
    await i18n.changeLanguage('ar');
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('storage-file-list')).toBeInTheDocument();
    });
    expect(screen.getAllByText(i18n.t('storage.title')).length).toBeGreaterThan(0);
    expect(screen.queryByText(i18n.t('storage.orphan'))).not.toBeInTheDocument();
    expect(screen.getByTestId('storage-download-doc-1')).toHaveTextContent(
      i18n.t('common.download'),
    );
    expect(i18n.t('storage.title')).toBe('التخزين');
  });

  it('downloads via authenticated blob helper', async () => {
    const { triggerBrowserDownload } = await import('@/lib/download');
    downloadDocumentFile.mockResolvedValue({
      blob: new Blob(['%PDF']),
      filename: 'policy.pdf',
      contentType: 'application/pdf',
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('storage-download-doc-1')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('storage-download-doc-1'));
    await waitFor(() => {
      expect(downloadDocumentFile).toHaveBeenCalledWith('doc-1');
    });
    expect(triggerBrowserDownload).toHaveBeenCalled();
  });

  it('scopes list queries to the workspace', async () => {
    renderPage();
    await waitFor(() => {
      expect(listDocuments).toHaveBeenCalled();
    });
    expect(listDocuments.mock.calls[0][0]).toEqual({
      limit: 25,
      offset: 0,
      q: undefined,
    });
    workspaceState.id = 'ws-b';
    renderPage();
    await waitFor(() => {
      expect(listDocuments.mock.calls.length).toBeGreaterThan(1);
    });
  });

  it('renders pagination when total exceeds page size', async () => {
    listDocuments.mockResolvedValue(
      page({
        items: Array.from({ length: 25 }, (_, i) => file({ id: `doc-${i}`, title: `File ${i}` })),
        total: 40,
      }),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('storage-pagination')).toBeInTheDocument();
    });
    expect(screen.getByTestId('storage-next')).toBeInTheDocument();
  });
});
