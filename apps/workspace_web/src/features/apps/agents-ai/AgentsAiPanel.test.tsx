import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import { ApiError } from '@/services/api/errors';
import type { AgentsAiUsage, CatalogApp } from '@/services/api/apps';
import { AgentsAiPanel } from './AgentsAiPanel';

const { useAgentsAiUsageMock } = vi.hoisted(() => ({
  useAgentsAiUsageMock: vi.fn(),
}));

vi.mock('../hooks/useAppsQueries', () => ({
  useAgentsAiUsage: (...args: unknown[]) => useAgentsAiUsageMock(...args),
}));

function app(status: CatalogApp['status'] = 'published'): CatalogApp {
  return {
    id: 'app-agents',
    slug: 'agents-ai',
    name: 'Agents AI',
    short_description: 'Agent loops',
    description: 'Agent loops with Geem RAG.',
    category: {
      slug: 'automation',
      name_key: 'apps.categories.automation',
      description_key: null,
      icon: null,
      sort_order: 40,
    },
    icon_url: null,
    billing_type: 'subscription',
    status,
    is_featured: true,
    sort_order: 40,
    plans: [
      {
        id: 'plan-team',
        code: 'agents-team',
        name: 'Agents Team',
        description: 'Team plan',
        billing_interval: 'monthly',
        price_amount: '199.00',
        currency: 'SAR',
        is_default: true,
        entitlements: { agent_requests_daily: 100 },
      },
    ],
    installation: { id: 'inst-1', status: 'active', installed_at: '2026-08-01T00:00:00Z' },
    installation_status: 'active',
    can_install: false,
    can_uninstall: true,
    access_requirement: 'subscription',
    access: null,
    connector: null,
    has_active_connection: false,
  };
}

function usage(
  overrides: Partial<AgentsAiUsage['access']> = {},
): AgentsAiUsage {
  return {
    access: {
      status: 'active',
      plan_id: 'plan-team',
      plan_code: 'agents-team',
      plan_name: 'Agents Team',
      plan_price_amount: '199.00',
      plan_currency: 'SAR',
      plan_billing_interval: 'monthly',
      current_period_start: '2026-08-01T00:00:00Z',
      current_period_end: '2026-09-01T00:00:00Z',
      commercially_entitled: true,
      installed: true,
      ...overrides,
    },
    agent_requests_daily: {
      used: 42,
      limit: 100,
      reset_at: '2026-08-26T00:00:00Z',
    },
    base_url: 'https://api.geem.ai/api/v1/agent',
    model: 'dalseen/geem-1.0',
  };
}

function renderPanel(catalogApp = app()) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <AgentsAiPanel app={catalogApp} />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('AgentsAiPanel', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    useAgentsAiUsageMock.mockReset();
    useAgentsAiUsageMock.mockReturnValue({
      data: usage(),
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('shows authoritative access, daily usage, API information, and setup links', () => {
    renderPanel();
    expect(screen.getByTestId('agents-ai-panel')).toBeInTheDocument();
    expect(screen.getByTestId('agents-ai-access-active')).toBeInTheDocument();
    expect(screen.getByLabelText('SAR 199.00')).toBeInTheDocument();
    expect(screen.getByTestId('agents-ai-daily-usage')).toHaveTextContent('42 / 100');
    expect(screen.getByText('https://api.geem.ai/api/v1/agent')).toHaveAttribute(
      'dir',
      'ltr',
    );
    expect(
      screen.getByText('https://api.geem.ai/api/v1/agent/models'),
    ).toHaveAttribute('dir', 'ltr');
    expect(screen.getByText('dalseen/geem-1.0')).toHaveAttribute('dir', 'ltr');
    expect(screen.getByRole('link', { name: 'API Keys' })).toHaveAttribute(
      'href',
      '/api/keys',
    );
    expect(screen.getByRole('link', { name: 'Experts' })).toHaveAttribute(
      'href',
      '/experts',
    );
    expect(
      screen.getByRole('link', { name: 'Integrator documentation' }),
    ).toHaveAttribute('href', 'https://geem.ai/en/agent-ai');
    expect(
      screen.getByRole('link', { name: 'Integrator documentation' }),
    ).toHaveAttribute('target', '_blank');
  });

  it('shows the subscribed price after the current plan stops new sales', () => {
    const catalogApp = app();
    catalogApp.plans = [];

    renderPanel(catalogApp);

    expect(screen.getByLabelText('SAR 199.00')).toBeInTheDocument();
    expect(screen.getByText(i18n.t('apps.billing.perMonth'))).toBeInTheDocument();
  });

  it('uses a typed localized error and supports retry', () => {
    const refetch = vi.fn();
    useAgentsAiUsageMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new ApiError('unavailable', {
        status: 503,
        code: 'app_runtime_access_unavailable',
      }),
      refetch,
    });
    renderPanel();
    expect(screen.getByTestId('agents-ai-usage-error')).toHaveTextContent(
      i18n.t('errors.appRuntimeAccessUnavailable'),
    );
    fireEvent.click(screen.getByRole('button', { name: i18n.t('apps.retry') }));
    expect(refetch).toHaveBeenCalled();
  });

  it('renders localized Arabic UI while technical identifiers remain LTR', async () => {
    await i18n.changeLanguage('ar');
    renderPanel();
    expect(screen.getByText(i18n.t('apps.agentsAi.usageTitle'))).toBeInTheDocument();
    expect(screen.getByText('dalseen/geem-1.0')).toHaveAttribute('dir', 'ltr');
    expect(
      screen.getByRole('link', { name: i18n.t('apps.agentsAi.documentation') }),
    ).toHaveAttribute('href', 'https://geem.ai/ar/agent-ai');
  });

  it('does not call the published usage surface for a coming-soon catalog row', () => {
    renderPanel(app('coming_soon'));
    expect(screen.getByTestId('agents-ai-coming-soon')).toBeInTheDocument();
    expect(useAgentsAiUsageMock).toHaveBeenCalledWith(false);
  });
});
