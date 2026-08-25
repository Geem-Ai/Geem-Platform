import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestMock = vi.fn();

vi.mock('@/services/api/client', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

import {
  AGENTS_AI_APP_SLUG,
  getAgentsAiUsage,
  hasActiveAgentsAiAccess,
  isAgentsAiApp,
  type AgentsAiUsage,
} from '@/services/api/apps';

function usage(overrides: Partial<AgentsAiUsage['access']> = {}): AgentsAiUsage {
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
      used: 7,
      limit: 100,
      reset_at: '2026-08-26T00:00:00Z',
    },
    base_url: 'https://api.geem.ai/api/v1/agent',
    model: 'dalseen/geem-1.0',
  };
}

describe('Agents AI API client', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('loads the session-authenticated App usage endpoint', async () => {
    const response = usage();
    apiRequestMock.mockResolvedValue(response);

    await expect(getAgentsAiUsage()).resolves.toEqual(response);
    expect(apiRequestMock).toHaveBeenCalledWith('/api/apps/agents-ai/usage');
  });

  it('requires active entitlement and installation for enablement controls', () => {
    expect(AGENTS_AI_APP_SLUG).toBe('agents-ai');
    expect(isAgentsAiApp({ slug: 'agents-ai' })).toBe(true);
    expect(isAgentsAiApp({ slug: 'chat-widget' })).toBe(false);
    expect(hasActiveAgentsAiAccess(usage())).toBe(true);
    expect(hasActiveAgentsAiAccess(usage({ installed: false }))).toBe(false);
    expect(hasActiveAgentsAiAccess(usage({ status: 'expired' }))).toBe(false);
    expect(
      hasActiveAgentsAiAccess(usage({ commercially_entitled: false })),
    ).toBe(false);
  });
});
