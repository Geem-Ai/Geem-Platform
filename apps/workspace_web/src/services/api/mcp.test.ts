import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestMock = vi.fn();

vi.mock('@/services/api/client', () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}));

import {
  createExpertMcpGrant,
  createMcpServer,
  listExpertMcpGrants,
  listMcpTools,
  updateMcpToolClassification,
} from './mcp';
import { queryKeys } from './query-keys';

describe('MCP API', () => {
  beforeEach(() => apiRequestMock.mockReset());

  it('sends the strict server-create contract without returning secrets', async () => {
    apiRequestMock.mockResolvedValue({ id: 'server-1' });
    const input = {
      display_name: 'CRM tools',
      server_url: 'https://mcp.example.com',
      auth: { mode: 'static' as const, header_name: 'Authorization', secret: 'secret' },
    };
    await createMcpServer(input);
    expect(apiRequestMock).toHaveBeenCalledWith('/api/apps/mcp/servers', {
      method: 'POST',
      json: input,
    });
  });

  it('uses server-scoped pagination and tool classification endpoints', async () => {
    apiRequestMock.mockResolvedValue({ items: [], total: 0, limit: 25, offset: 25 });
    await listMcpTools('server/1', { limit: 25, offset: 25 });
    expect(apiRequestMock).toHaveBeenCalledWith('/api/apps/mcp/servers/server%2F1/tools?limit=25&offset=25');

    await updateMcpToolClassification('tool/1', 'write');
    expect(apiRequestMock).toHaveBeenLastCalledWith('/api/apps/mcp/tools/tool%2F1', {
      method: 'PATCH',
      json: { classification: 'write' },
    });
  });

  it('unwraps grant lists and sends the exact grant input', async () => {
    apiRequestMock.mockResolvedValueOnce({ items: [{ id: 'grant-1' }] });
    await expect(listExpertMcpGrants('expert-1')).resolves.toEqual([{ id: 'grant-1' }]);
    const input = {
      tool_id: 'tool-1',
      allow_workspace_chat: true,
      allow_public_api: false,
      unattended_write_allowed: false,
      outbound_data_acknowledged: true,
    };
    apiRequestMock.mockResolvedValueOnce({ id: 'grant-1' });
    await createExpertMcpGrant('expert-1', input);
    expect(apiRequestMock).toHaveBeenLastCalledWith('/api/experts/expert-1/mcp-grants', {
      method: 'POST',
      json: input,
    });
  });

  it('scopes every MCP cache key to the workspace', () => {
    expect(queryKeys.mcpServers('ws-1', { limit: 25, offset: 0 })[0]).toBe('workspace');
    expect(queryKeys.mcpServers('ws-1', { limit: 25, offset: 0 })[1]).toBe('ws-1');
    expect(queryKeys.expertMcpGrants('ws-2', 'expert-1')).toEqual([
      'workspace', 'ws-2', 'experts', 'expert-1', 'mcp-grants',
    ]);
  });
});
