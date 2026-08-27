import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/lib/i18n';
import type { AppConnection } from '@/services/api/apps';
import type { McpGrant } from '@/services/api/mcp';
import { McpExpertToolsPanel } from './McpExpertToolsPanel';

const mocks = vi.hoisted(() => ({
  createBinding: vi.fn(),
  getChatWidget: vi.fn(),
}));

const grant: McpGrant = {
  id: 'grant-id',
  expert_id: 'expert-id',
  app_connection_id: 'mcp-connection-id',
  tool_id: 'tool-id',
  tool_name: 'list_branches',
  llm_tool_name: 'github_list_branches',
  connection_display_name: 'GitHub',
  state: 'active',
  approved_classification: 'read',
  allow_workspace_chat: true,
  allow_public_api: false,
  unattended_write_allowed: false,
};

const whatsappConnection: AppConnection = {
  id: 'app-connection-id',
  channel_binding_id: 'channel-binding-id',
  workspace_id: 'workspace-id',
  app_installation_id: 'whatsapp-installation-id',
  app_slug: 'whatsapp',
  connector_key: 'openwa',
  connector_kind: 'channel',
  display_name: 'Support line',
  external_account_id: '966500000000',
  external_account_name: 'Support',
  auth_mode: 'custom',
  status: 'active',
  health: 'healthy',
  connected_at: null,
  disconnected_at: null,
  last_health_check_at: null,
  last_success_at: null,
  last_error_code: null,
  last_error_message: null,
  last_error_at: null,
  credentials_expires_at: null,
  created_at: null,
  capabilities: {
    can_disconnect: true,
    can_health_check: false,
    can_sync: false,
    can_reconnect: false,
  },
};

vi.mock('@/features/authz/usePermissions', () => ({
  usePermissions: () => ({ can: () => true }),
}));

vi.mock('@/features/workspaces/WorkspaceProvider', () => ({
  useWorkspace: () => ({ currentWorkspace: { id: 'workspace-id' } }),
}));

vi.mock('@/features/apps/connections/hooks/useConnectionQueries', () => ({
  useAppConnections: () => ({
    data: {
      items: [whatsappConnection],
      total: 1,
      limit: 50,
      offset: 0,
    },
  }),
}));

vi.mock('@/services/api/apps', async () => {
  const actual = await vi.importActual<typeof import('@/services/api/apps')>(
    '@/services/api/apps',
  );
  return {
    ...actual,
    getChatWidget: () => mocks.getChatWidget(),
  };
});

vi.mock('../hooks/useMcpQueries', () => ({
  useMcpServers: () => ({ data: { items: [] } }),
  useMcpTools: () => ({ data: { items: [] } }),
  useExpertMcpGrants: () => ({ data: [grant], isError: false }),
  useExpertMcpSurfaceBindings: () => ({ data: [] }),
  useCreateExpertMcpGrant: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRevokeExpertMcpGrant: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCreateExpertMcpSurfaceBinding: () => ({
    mutateAsync: mocks.createBinding,
    isPending: false,
  }),
  useRevokeExpertMcpSurfaceBinding: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

async function choose(testId: string, optionName: string) {
  const trigger = screen.getByTestId(testId);
  fireEvent.keyDown(trigger, { key: 'Enter' });
  fireEvent.click(await screen.findByRole('option', { name: optionName }));
  await waitFor(() => expect(trigger).toHaveTextContent(optionName));
}

describe('McpExpertToolsPanel exact WhatsApp binding', () => {
  beforeAll(() => {
    Object.defineProperties(HTMLElement.prototype, {
      hasPointerCapture: { configurable: true, value: () => false },
      setPointerCapture: { configurable: true, value: () => undefined },
      releasePointerCapture: { configurable: true, value: () => undefined },
      scrollIntoView: { configurable: true, value: () => undefined },
    });
  });

  beforeEach(async () => {
    mocks.createBinding.mockReset().mockResolvedValue(undefined);
    mocks.getChatWidget.mockReset().mockResolvedValue(null);
    await i18n.changeLanguage('en');
  });

  it('submits ChannelBinding.id and never AppConnection.id', async () => {
    render(
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={new QueryClient()}>
          <McpExpertToolsPanel expertId="expert-id" />
        </QueryClientProvider>
      </I18nextProvider>,
    );

    await choose('mcp-binding-grant', 'list_branches');
    await choose('mcp-binding-surface', 'WhatsApp');
    await choose('mcp-binding-target', 'Support line');
    fireEvent.click(screen.getByLabelText(
      'I understand public users can trigger this tool and that writes require a workspace operator',
    ));
    fireEvent.click(screen.getAllByLabelText(
      'I understand data will be sent to this external server',
    )[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Bind surface' }));

    await waitFor(() => expect(mocks.createBinding).toHaveBeenCalledWith({
      mcp_tool_grant_id: 'grant-id',
      surface_kind: 'whatsapp_openwa',
      widget_instance_id: null,
      channel_binding_id: 'channel-binding-id',
      write_policy: 'deny',
      public_risk_acknowledged: true,
      outbound_data_acknowledged: true,
    }));
    expect(mocks.createBinding).not.toHaveBeenCalledWith(
      expect.objectContaining({ channel_binding_id: 'app-connection-id' }),
    );
  });
});
