import { describe, expect, it } from 'vitest';
import type { McpServer } from '@/services/api/mcp';
import { displayedServerStatus } from './mcpServerStatus';

function server(status: string, health: string): McpServer {
  return {
    id: 'server-id',
    display_name: 'Server',
    auth: { mode: 'oauth' },
    status,
    health,
  };
}

describe('displayedServerStatus', () => {
  it('does not mask connecting lifecycle state with unknown health', () => {
    expect(displayedServerStatus(server('connecting', 'unknown'))).toBe(
      'connecting',
    );
  });

  it('uses health for an active connection', () => {
    expect(displayedServerStatus(server('active', 'healthy'))).toBe('healthy');
  });

  it('keeps degraded lifecycle state authoritative', () => {
    expect(displayedServerStatus(server('degraded', 'unknown'))).toBe(
      'degraded',
    );
  });
});
