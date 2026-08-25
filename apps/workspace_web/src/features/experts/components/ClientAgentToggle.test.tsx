import { fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { AgentsAiUsage } from '@/services/api/apps';
import { ClientAgentToggle } from './ClientAgentToggle';

function usage(
  overrides: Partial<AgentsAiUsage['access']> = {},
): AgentsAiUsage {
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
      ...overrides,
    },
    agent_requests_daily: {
      used: 3,
      limit: 50,
      reset_at: '2026-08-26T00:00:00Z',
    },
    base_url: 'https://api.geem.ai/api/v1/agent',
    model: 'dalseen/geem-1.0',
  };
}

function renderToggle(props: {
  checked: boolean;
  onCheckedChange?: (checked: boolean) => void;
  usage?: AgentsAiUsage;
  accessLoading?: boolean;
  accessError?: boolean;
}) {
  const onCheckedChange = props.onCheckedChange ?? vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <ClientAgentToggle
          checked={props.checked}
          onCheckedChange={onCheckedChange}
          usage={props.usage}
          accessLoading={props.accessLoading ?? false}
          accessError={props.accessError ?? false}
        />
      </MemoryRouter>
    </I18nextProvider>,
  );
  return onCheckedChange;
}

describe('ClientAgentToggle', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('allows false to true only while Agents AI is active and installed', () => {
    const onChange = renderToggle({ checked: false, usage: usage() });
    const checkbox = screen.getByTestId('client-agent-enabled');
    expect(checkbox).toBeEnabled();
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(true);
    expect(screen.getByTestId('client-agent-access-active')).toBeInTheDocument();
  });

  it('blocks enabling without access and shows the recovery link', () => {
    renderToggle({
      checked: false,
      usage: usage({ status: 'expired', installed: true }),
    });
    expect(screen.getByTestId('client-agent-enabled')).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Renew Agents AI' })).toHaveAttribute(
      'href',
      '/apps/agents-ai',
    );
  });

  it('lets a stored true value be turned off after access expires', () => {
    const onChange = renderToggle({
      checked: true,
      usage: usage({ status: 'expired', installed: true }),
    });
    const checkbox = screen.getByTestId('client-agent-enabled');
    expect(checkbox).toBeEnabled();
    expect(screen.getByTestId('client-agent-access-required')).toHaveTextContent(
      'stored',
    );
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it('renders the Arabic label while keeping the App route stable', async () => {
    await i18n.changeLanguage('ar');
    renderToggle({ checked: false, usage: usage() });
    expect(screen.getByText(i18n.t('experts.clientAgent.label'))).toBeInTheDocument();
  });
});
