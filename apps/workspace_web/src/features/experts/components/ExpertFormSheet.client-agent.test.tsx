import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { AgentsAiUsage } from '@/services/api/apps';
import type { Expert } from '@/services/api/types';
import { ExpertFormSheet } from './ExpertFormSheet';

const {
  useExpertMock,
  updateMutate,
  useAgentsAiUsageMock,
} = vi.hoisted(() => ({
  useExpertMock: vi.fn(),
  updateMutate: vi.fn(),
  useAgentsAiUsageMock: vi.fn(),
}));

vi.mock('../hooks/useExpert', () => ({
  useExpert: (...args: unknown[]) => useExpertMock(...args),
}));

vi.mock('../hooks/useExpertMutations', () => ({
  useCreateExpert: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateExpert: () => ({ mutate: updateMutate, isPending: false }),
}));

vi.mock('@/features/usage/hooks/useUsageQueries', () => ({
  useUsageSummary: () => ({ data: undefined }),
}));

vi.mock('@/features/apps/hooks/useAppsQueries', () => ({
  useAgentsAiUsage: (...args: unknown[]) => useAgentsAiUsageMock(...args),
}));

function expert(): Expert {
  return {
    id: 'expert-1',
    type: 'workspace',
    ownership: 'workspace',
    workspace_id: 'ws-1',
    name: 'Operations Expert',
    description: 'Helps operations',
    icon_url: null,
    system_instructions: 'Be precise.',
    rag_config: {
      top_k: 12,
      rerank_top_n: 4,
      similarity_threshold: 0.4,
      client_agent: { enabled: true },
    },
    status: 'ready',
    visibility: 'workspace',
    availability_mode: 'workspace',
    knowledge_mode: 'rag',
    created_by: 'user-1',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    knowledge_document_count: 1,
  };
}

function activeUsage(): AgentsAiUsage {
  return {
    access: {
      status: 'active',
      plan_id: 'plan-1',
      plan_code: 'agents-team',
      plan_name: 'Agents Team',
      plan_price_amount: '199.00',
      plan_currency: 'SAR',
      plan_billing_interval: 'monthly',
      current_period_start: '2026-08-01T00:00:00Z',
      current_period_end: '2026-09-01T00:00:00Z',
      commercially_entitled: true,
      installed: true,
    },
    agent_requests_daily: {
      used: 1,
      limit: 100,
      reset_at: '2026-08-26T00:00:00Z',
    },
    base_url: 'https://api.geem.ai/api/v1/agent',
    model: 'dalseen/geem-1.0',
  };
}

describe('ExpertFormSheet client_agent persistence', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    updateMutate.mockReset();
    useExpertMock.mockReset();
    useAgentsAiUsageMock.mockReset();
    const expertQuery = {
      data: expert(),
      isLoading: false,
      isError: false,
    };
    useExpertMock.mockReturnValue(expertQuery);
    useAgentsAiUsageMock.mockReturnValue({
      data: activeUsage(),
      isLoading: false,
      isError: false,
    });
  });

  it('keeps an enabled client_agent flag when saving unrelated Expert fields', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <ExpertFormSheet
            mode="edit"
            open
            expertId="expert-1"
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </I18nextProvider>,
    );

    const checkbox = await screen.findByTestId('client-agent-enabled');
    expect(checkbox).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: i18n.t('common.save') }));

    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          rag_config: {
            top_k: 12,
            rerank_top_n: 4,
            similarity_threshold: 0.4,
            client_agent: { enabled: true },
          },
        }),
        expect.any(Object),
      );
    });
  });
});
