import type { AppConnection } from '@/services/api/apps';

export type McpSurfaceTarget = {
  id: string;
  label: string;
};

/**
 * Build exact WhatsApp MCP targets.
 *
 * AppConnection.id identifies the provider account, while the MCP surface API
 * authorizes a ChannelBinding.id. A connection without the latter is not a
 * valid selectable surface and must never fall back to the connection ID.
 */
export function whatsappMcpSurfaceTargets(
  connections: readonly AppConnection[],
): McpSurfaceTarget[] {
  return connections.flatMap((connection) => {
    const bindingId = connection.channel_binding_id?.trim();
    if (!bindingId) return [];
    return [
      {
        id: bindingId,
        label:
          connection.display_name ||
          connection.external_account_name ||
          bindingId,
      },
    ];
  });
}
