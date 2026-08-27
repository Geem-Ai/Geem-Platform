import { describe, expect, it } from 'vitest';
import type { AppConnection } from '@/services/api/apps';
import { whatsappMcpSurfaceTargets } from './surfaceTargets';

function connection(
  id: string,
  channelBindingId: string | null | undefined,
): AppConnection {
  return {
    id,
    channel_binding_id: channelBindingId,
    workspace_id: 'workspace-1',
    app_installation_id: 'installation-1',
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
}

describe('whatsappMcpSurfaceTargets', () => {
  it('uses the exact ChannelBinding id instead of the AppConnection id', () => {
    expect(
      whatsappMcpSurfaceTargets([
        connection('app-connection-id', 'channel-binding-id'),
      ]),
    ).toEqual([{ id: 'channel-binding-id', label: 'Support line' }]);
  });

  it('does not expose a connection when its exact binding is unavailable', () => {
    expect(
      whatsappMcpSurfaceTargets([
        connection('must-not-be-used', null),
        connection('also-must-not-be-used', '  '),
      ]),
    ).toEqual([]);
  });
});
