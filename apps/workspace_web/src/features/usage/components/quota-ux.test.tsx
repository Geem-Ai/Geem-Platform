import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ChatMessage } from '@/features/chat/components/ChatMessage';
import { ExpertFormSheet } from '@/features/experts/components/ExpertFormSheet';
import { UploadKnowledgeDialog } from '@/features/experts/components/UploadKnowledgeDialog';
import { errorMessageKey } from '@/services/api/errors';
import type { Meter, UsageSummary } from '@/services/api/usage';
import { QuotaAlert } from './QuotaAlert';

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    currentWorkspace: { id: 'ws-a', name: 'Acme', slug: 'acme', role: 'owner' },
    currentMembership: {
      id: 'm1',
      workspace_id: 'ws-a',
      user_id: 'u1',
      role: 'owner',
      created_at: '2026-01-01T00:00:00Z',
    },
  }),
}));

const getUsageSummary = vi.fn();
const getUsageHistory = vi.fn();
const getSubscription = vi.fn();

vi.mock('@/services/api/usage', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/usage')>(
    '@/services/api/usage',
  );
  return {
    ...actual,
    getUsageSummary: () => getUsageSummary(),
    getUsageHistory: (params?: { limit?: number; offset?: number }) =>
      getUsageHistory(params),
    getSubscription: () => getSubscription(),
  };
});

vi.mock('@/features/experts/hooks/useExpert', () => ({
  useExpert: () => ({ data: undefined, isLoading: false, isError: false }),
}));

vi.mock('@/features/experts/hooks/useExpertMutations', () => ({
  useCreateExpert: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateExpert: () => ({ mutate: vi.fn(), isPending: false }),
  useUploadExpertDocument: () => ({ mutate: vi.fn(), isPending: false }),
}));

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{ui}</MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

function meter(partial: Partial<Meter> = {}): Meter {
  return {
    limit: 5,
    used: 5,
    reserved: 0,
    remaining: 0,
    period_start: null,
    period_end: null,
    ...partial,
  };
}

function exhaustedSummary(): UsageSummary {
  const zero = meter();
  return {
    ai_tokens: { daily: zero, weekly: zero, monthly: zero },
    ai: { daily: zero, weekly: zero, monthly: zero },
    experts: meter({ used: 2, limit: 2, remaining: 0 }),
    storage_bytes: meter({ used: 100, limit: 100, remaining: 0 }),
    storage: {
      limit_bytes: 100,
      used_bytes: 100,
      remaining_bytes: 0,
      reserved_bytes: 0,
      percentage: 100,
    },
    credits: { balance: 0 },
  };
}

describe('quota UX surfaces', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    getUsageSummary.mockReset();
    getUsageHistory.mockReset();
    getSubscription.mockReset();
    getUsageSummary.mockResolvedValue(exhaustedSummary());
    getUsageHistory.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });
    getSubscription.mockResolvedValue({
      id: 'sub',
      status: 'active',
      plan: { id: 'p', code: 'bootstrap_dev', name: 'Developer', status: 'active' },
      starts_at: '2026-01-01T00:00:00Z',
      current_period_start: '2026-08-01T00:00:00Z',
      current_period_end: '2026-09-01T00:00:00Z',
      ends_at: null,
    });
  });

  it('maps quota error codes to localized keys', () => {
    expect(errorMessageKey('quota_exceeded')).toBe('errors.quotaExceeded');
    expect(errorMessageKey('insufficient_credits')).toBe('errors.insufficientCredits');
    expect(errorMessageKey('expert_limit_reached')).toBe('errors.expertLimitReached');
    expect(errorMessageKey('storage_quota_exceeded')).toBe('errors.storageQuotaExceeded');
    expect(i18n.t('errors.quotaExceeded')).not.toMatch(/server error/i);
  });

  it('renders Chat QUOTA_EXCEEDED without a generic server error or retry', () => {
    wrap(
      <ChatMessage
        message={{
          id: 'a1',
          role: 'assistant',
          content: '',
          citations: [],
          status: 'failed',
          created_at: '2026-08-13T10:00:00Z',
          errorCode: 'quota_exceeded',
          errorMessage: 'AI quota exceeded',
        }}
        onRetry={vi.fn()}
      />,
    );
    const alert = screen.getByTestId('chat-quota-error');
    expect(alert).toHaveTextContent(i18n.t('errors.quotaExceeded'));
    expect(alert).not.toHaveTextContent(/server error/i);
    expect(screen.queryByRole('button', { name: i18n.t('chat.retry') })).not.toBeInTheDocument();
  });

  it('renders Expert EXPERT_LIMIT_REACHED in the create sheet', async () => {
    wrap(<ExpertFormSheet mode="create" open onOpenChange={vi.fn()} />);
    expect(await screen.findByTestId('quota-alert')).toHaveAttribute(
      'data-code',
      'expert_limit_reached',
    );
    expect(screen.getByTestId('quota-alert')).toHaveTextContent(
      i18n.t('errors.expertLimitReached'),
    );
  });

  it('renders storage STORAGE_QUOTA_EXCEEDED on knowledge upload', async () => {
    wrap(
      <UploadKnowledgeDialog expertId="exp-1" open onOpenChange={vi.fn()} />,
    );
    expect(await screen.findByTestId('upload-storage-meter')).toBeInTheDocument();
    expect(screen.getByTestId('quota-alert')).toHaveAttribute(
      'data-code',
      'storage_quota_exceeded',
    );
    expect(screen.getByTestId('quota-alert')).toHaveTextContent(
      i18n.t('errors.storageQuotaExceeded'),
    );
  });

  it('keeps quota warning presentation centralized on QuotaAlert', () => {
    wrap(<QuotaAlert level="approaching" />);
    expect(screen.getByTestId('quota-alert')).toHaveAttribute('data-level', 'approaching');
    expect(screen.getByTestId('quota-alert')).toHaveTextContent('Approaching limit');
  });
});
