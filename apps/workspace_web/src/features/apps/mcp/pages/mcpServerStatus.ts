import type { McpServer } from '@/services/api/mcp';

export function displayedServerStatus(server: McpServer): string {
  // Lifecycle state is authoritative while a connection is not active. Health
  // is meaningful only after the OAuth/discovery lifecycle reaches active.
  if (server.status && server.status !== 'active') return server.status;
  return server.health || server.status || 'unknown';
}
