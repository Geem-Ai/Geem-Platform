import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { McpGrant } from '@/services/api/mcp';
import { McpServerDetailPage } from './McpServerDetailPage';

const mocks = vi.hoisted(() => ({
  grants: [] as McpGrant[],
  createGrant: vi.fn(),
  revokeGrant: vi.fn(),
}));

vi.mock('@/components/shared/DocumentTitle', () => ({
  DocumentTitle: () => null,
}));

vi.mock('@/features/authz/usePermissions', () => ({
  usePermissions: () => ({ can: () => true }),
}));

vi.mock('@/features/experts/hooks/useExperts', () => ({
  useExperts: () => ({
    data: [{ id: 'expert-id', name: 'Legal Expert', ownership: 'workspace' }],
    isLoading: false,
  }),
}));

vi.mock('../hooks/useMcpQueries', () => ({
  useMcpServer: () => ({
    data: {
      id: 'server-id',
      display_name: 'GitHub',
      endpoint_host: 'api.githubcopilot.com',
      auth: { mode: 'oauth', reauthorization_required: false },
      status: 'active',
      health: 'healthy',
      protocol_version: '2026-07-28',
      session_mode: 'modern',
      reauthorization_required: false,
    },
    error: null,
  }),
  useMcpTools: () => ({
    data: {
      items: [{
        id: 'tool-id',
        title: 'Create issue',
        description: 'Creates a GitHub issue.',
        tool_name: 'issue_write',
        llm_tool_name: 'github_issue_write',
        compatibility_status: 'compatible',
        classification: 'write',
        status: 'active',
      }],
      total: 1,
      limit: 25,
      offset: 0,
    },
    isLoading: false,
    isFetching: false,
    error: null,
  }),
  useExpertMcpGrants: () => ({ data: mocks.grants, isLoading: false }),
  useDiscoverMcpTools: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateMcpToolClassification: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useCreateExpertMcpGrant: () => ({
    mutateAsync: mocks.createGrant,
    isPending: false,
  }),
  useRevokeExpertMcpGrant: () => ({
    mutateAsync: mocks.revokeGrant,
    isPending: false,
  }),
}));

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/apps/mcp/server-id']}>
        <Routes>
          <Route path="/apps/mcp/:connectionId" element={<McpServerDetailPage />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

function selectExpert() {
  fireEvent.click(screen.getByTestId('mcp-expert-select'));
  fireEvent.click(screen.getByRole('option', { name: 'Legal Expert' }));
}

function acknowledgeOutboundData() {
  fireEvent.click(screen.getByLabelText(
    'I understand data will be sent to this external server',
  ));
}

function grant(state: McpGrant['state']): McpGrant {
  return {
    id: 'grant-id',
    expert_id: 'expert-id',
    app_connection_id: 'server-id',
    tool_id: 'tool-id',
    tool_name: 'issue_write',
    llm_tool_name: 'github_issue_write',
    connection_display_name: 'GitHub',
    state,
    approved_classification: 'write',
    allow_workspace_chat: true,
    allow_public_api: false,
    unattended_write_allowed: false,
  };
}

describe('McpServerDetailPage grant controls', () => {
  beforeAll(() => {
    Object.defineProperties(HTMLElement.prototype, {
      hasPointerCapture: { configurable: true, value: () => false },
      setPointerCapture: { configurable: true, value: () => undefined },
      releasePointerCapture: { configurable: true, value: () => undefined },
      scrollIntoView: { configurable: true, value: () => undefined },
    });
  });

  beforeEach(async () => {
    mocks.grants = [];
    mocks.createGrant.mockReset().mockResolvedValue(undefined);
    mocks.revokeGrant.mockReset().mockResolvedValue(undefined);
    await i18n.changeLanguage('en');
  });

  it('clarifies that grant options are saved from each tool card', () => {
    renderPage();

    expect(screen.getByRole('heading', { name: 'Grant options' })).toBeInTheDocument();
    expect(screen.getByText(
      'Choose a Workspace Expert and the access options to apply, then grant, save, or reapprove each tool from its card.',
    )).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Save$/ })).not.toBeInTheDocument();
  });

  it('grants an ungranted or revoked tool with the selected options', async () => {
    mocks.grants = [grant('revoked')];
    renderPage();
    selectExpert();
    expect(screen.getByRole('button', {
      name: 'Grant tool for Create issue',
    })).toBeDisabled();
    acknowledgeOutboundData();

    fireEvent.click(screen.getByRole('button', { name: 'Grant tool for Create issue' }));

    await waitFor(() => expect(mocks.createGrant).toHaveBeenCalledWith({
      tool_id: 'tool-id',
      allow_workspace_chat: true,
      allow_public_api: false,
      unattended_write_allowed: false,
      outbound_data_acknowledged: true,
    }));
    expect(mocks.revokeGrant).not.toHaveBeenCalled();
  });

  it('saves active grant changes and keeps revoke as a separate action', async () => {
    mocks.grants = [grant('active')];
    renderPage();
    selectExpert();
    fireEvent.click(screen.getByLabelText('Public API'));
    acknowledgeOutboundData();

    fireEvent.click(screen.getByRole('button', {
      name: 'Save changes for Create issue',
    }));

    await waitFor(() => expect(mocks.createGrant).toHaveBeenCalledWith({
      tool_id: 'tool-id',
      allow_workspace_chat: true,
      allow_public_api: true,
      unattended_write_allowed: false,
      outbound_data_acknowledged: true,
    }));

    fireEvent.click(screen.getByRole('button', { name: 'Revoke for Create issue' }));
    await waitFor(() => expect(mocks.revokeGrant).toHaveBeenCalledWith('grant-id'));
  });

  it('reapproves a stale grant through the grant upsert', async () => {
    mocks.grants = [grant('stale_definition')];
    renderPage();
    selectExpert();
    acknowledgeOutboundData();

    fireEvent.click(screen.getByRole('button', { name: 'Reapprove for Create issue' }));

    await waitFor(() => expect(mocks.createGrant).toHaveBeenCalledWith(
      expect.objectContaining({ tool_id: 'tool-id' }),
    ));
    expect(mocks.revokeGrant).not.toHaveBeenCalled();
  });
});
