import { apiRequest } from './client';

export const MCP_CONNECTORS_APP_SLUG = 'mcp-connectors';

export type McpAuthMode = 'none' | 'static' | 'oauth';
export type McpOauthStrategy =
  | 'cimd'
  | 'pre_registered'
  | 'dynamic_registration';
export type McpToolClassification = 'read_only' | 'write' | 'unknown';
export type McpToolCompatibility =
  | 'compatible'
  | 'unsupported_schema'
  | 'unsupported_capability'
  | 'malformed'
  | string;
export type McpGrantState =
  | 'pending_review'
  | 'active'
  | 'revoked'
  | 'stale_definition'
  | 'stale_classification'
  | 'stale_principal'
  | string;
export type McpSurfaceKind = 'chat_widget' | 'whatsapp_openwa';
export type McpWritePolicy = 'deny' | 'workspace_operator_approval';

export type McpServer = {
  id: string;
  display_name: string;
  endpoint_host?: string | null;
  auth: {
    mode: McpAuthMode | string;
    strategy?: McpOauthStrategy | string | null;
    header_name?: string | null;
    secret_hint?: string | null;
    issuer_host?: string | null;
    reauthorization_required?: boolean;
  };
  status: string;
  health: string;
  protocol_version?: string | null;
  session_mode?: string | null;
  external_identity_label?: string | null;
  inventory_refreshed_at?: string | null;
  discovered_tool_count?: number;
  capabilities?: Record<string, unknown>;
  external_account_name?: string | null;
  issuer?: string | null;
  credential_epoch?: number;
  reauthorization_required?: boolean;
  last_health_check_at?: string | null;
  last_success_at?: string | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  created_at?: string | null;
  authorization_url?: string | null;
};

export type McpServerList = {
  items: McpServer[];
  total: number;
  limit: number;
  offset: number;
  used?: number;
  connection_limit?: number | null;
};

export type McpStaticAuthInput = {
  mode: 'static';
  header_name: string;
  secret: string;
};

export type McpOauthAuthInput = {
  mode: 'oauth';
  strategy: McpOauthStrategy;
  client_id?: string | null;
  client_secret?: string | null;
  scopes?: string[];
  expected_issuer?: string | null;
};

export type McpServerCreateInput = {
  display_name: string;
  server_url: string;
  resource_uri?: string | null;
  auth:
    | { mode: 'none' }
    | McpStaticAuthInput
    | McpOauthAuthInput;
};

export type McpAuthStatus = {
  connection_id: string;
  auth_mode: McpAuthMode | string;
  strategy?: McpOauthStrategy | string | null;
  status: string;
  issuer?: string | null;
  resource_url?: string | null;
  external_identity_label?: string | null;
  credential_epoch?: number;
  reauthorization_required?: boolean;
  redacted_credential?: string | null;
};

export type McpDiscoveryResult = {
  server: McpServer;
  generation: number;
  tools_seen: number;
  tools_created: number;
  tools_updated: number;
  tools_withdrawn: number;
  complete: boolean;
  warnings: string[];
};

export type McpTool = {
  id: string;
  workspace_id: string;
  app_connection_id: string;
  tool_name: string;
  llm_tool_name: string;
  title: string | null;
  description: string | null;
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
  annotations?: Record<string, unknown> | null;
  protocol_version?: string | null;
  compatibility_status: McpToolCompatibility;
  compatibility_reason?: string | null;
  classification: McpToolClassification;
  definition_hash?: string;
  status: 'active' | 'stale' | 'withdrawn' | string;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
};

export type McpToolList = {
  items: McpTool[];
  total: number;
  limit: number;
  offset: number;
};

export type McpUsage = {
  access?: {
    status: string;
    plan_code?: string | null;
    plan_name?: string | null;
    current_period_start?: string | null;
    current_period_end?: string | null;
    installed?: boolean;
  };
  connections: { used: number; limit: number };
  tool_calls_daily: { used: number; limit: number; reset_at: string };
};

export type McpGrant = {
  id: string;
  expert_id: string;
  app_connection_id: string;
  tool_id: string;
  tool_name: string;
  llm_tool_name: string;
  connection_display_name: string;
  state: McpGrantState;
  approved_classification: McpToolClassification | string;
  allow_workspace_chat: boolean;
  allow_public_api: boolean;
  unattended_write_allowed: boolean;
  outbound_data_acknowledged_at?: string | null;
  approved_at?: string | null;
  approved_definition_hash?: string | null;
  approved_credential_epoch?: number | null;
  unattended_write_acknowledged_at?: string | null;
  revoked_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type McpGrantCreateInput = {
  tool_id: string;
  allow_workspace_chat: boolean;
  allow_public_api: boolean;
  unattended_write_allowed: boolean;
  outbound_data_acknowledged: boolean;
  unattended_write_risk_acknowledged?: boolean;
};

export type McpSurfaceBinding = {
  id: string;
  workspace_id: string;
  expert_id: string;
  mcp_tool_grant_id: string;
  surface_kind: McpSurfaceKind;
  widget_instance_id?: string | null;
  channel_binding_id?: string | null;
  state: string;
  write_policy: McpWritePolicy;
  public_risk_acknowledged_at?: string | null;
  outbound_data_acknowledged_at?: string | null;
  target_label?: string | null;
};

export type McpSurfaceBindingCreateInput = {
  mcp_tool_grant_id: string;
  surface_kind: McpSurfaceKind;
  widget_instance_id?: string | null;
  channel_binding_id?: string | null;
  write_policy: McpWritePolicy;
  public_risk_acknowledged: boolean;
  outbound_data_acknowledged: boolean;
};

export type McpExternalApproval = {
  id: string;
  conversation_id?: string | null;
  message_id?: string | null;
  status: string;
  surface_kind: McpSurfaceKind | string;
  surface_label: string;
  sender_label?: string | null;
  connection_name?: string | null;
  tool_name?: string | null;
  arguments: Record<string, unknown> | unknown[] | null;
  expires_at?: string | null;
  created_at?: string | null;
  decided_at?: string | null;
  outcome_message?: string | null;
};

export type McpExternalApprovalList = {
  items: McpExternalApproval[];
  total: number;
  limit: number;
  offset: number;
};

export type McpExternalDelivery = {
  id: string;
  status: string;
  surface_kind: McpSurfaceKind | string;
  surface_label: string;
  sequence?: number | null;
  segment_index?: number | null;
  provider_message_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  resolved_at?: string | null;
};

export type McpExternalDeliveryList = {
  items: McpExternalDelivery[];
  total: number;
  limit: number;
  offset: number;
};

type PagingParams = { limit?: number; offset?: number; q?: string };

function paging(params?: PagingParams): string {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  const search = params?.q?.trim();
  if (search) query.set('q', search);
  const value = query.toString();
  return value ? `?${value}` : '';
}

export function listMcpServers(params?: { limit?: number; offset?: number }) {
  return apiRequest<McpServerList>(`/api/apps/mcp/servers${paging(params)}`);
}

export function getMcpServer(connectionId: string) {
  return apiRequest<McpServer>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}`,
  );
}

export function createMcpServer(input: McpServerCreateInput) {
  return apiRequest<McpServer>('/api/apps/mcp/servers', {
    method: 'POST',
    json: input,
  });
}

export function deleteMcpServer(connectionId: string) {
  return apiRequest<void>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}`,
    { method: 'DELETE' },
  );
}

export function startMcpOauth(connectionId: string, returnPath?: string) {
  return apiRequest<{ authorization_url: string }>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}/oauth/start`,
    { method: 'POST', json: { return_path: returnPath ?? null } },
  );
}

export function reauthorizeMcpServer(
  connectionId: string,
  body?: { scopes?: string[]; return_path?: string | null },
) {
  return apiRequest<{ authorization_url: string }>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}/reauthorize`,
    { method: 'POST', json: body ?? {} },
  );
}

export function getMcpAuthStatus(connectionId: string) {
  return apiRequest<McpAuthStatus>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}/auth-status`,
  );
}

export function discoverMcpTools(connectionId: string) {
  return apiRequest<McpDiscoveryResult>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}/discover`,
    { method: 'POST' },
  );
}

export function listMcpTools(
  connectionId: string,
  params?: PagingParams,
) {
  return apiRequest<McpToolList>(
    `/api/apps/mcp/servers/${encodeURIComponent(connectionId)}/tools${paging(params)}`,
  );
}

export function updateMcpToolClassification(
  toolId: string,
  classification: McpToolClassification,
) {
  return apiRequest<McpTool>(`/api/apps/mcp/tools/${encodeURIComponent(toolId)}`, {
    method: 'PATCH',
    json: { classification },
  });
}

export function getMcpUsage() {
  return apiRequest<McpUsage>('/api/apps/mcp/usage');
}

export function listExpertMcpGrants(expertId: string) {
  return apiRequest<{ items: McpGrant[] }>(
    `/api/experts/${encodeURIComponent(expertId)}/mcp-grants`,
  ).then((result) => result.items);
}

export function createExpertMcpGrant(
  expertId: string,
  input: McpGrantCreateInput,
) {
  return apiRequest<McpGrant>(
    `/api/experts/${encodeURIComponent(expertId)}/mcp-grants`,
    { method: 'POST', json: input },
  );
}

export function revokeExpertMcpGrant(expertId: string, grantId: string) {
  return apiRequest<void>(
    `/api/experts/${encodeURIComponent(expertId)}/mcp-grants/${encodeURIComponent(grantId)}`,
    { method: 'DELETE' },
  );
}

export function listExpertMcpSurfaceBindings(expertId: string) {
  return apiRequest<McpSurfaceBinding[]>(
    `/api/experts/${encodeURIComponent(expertId)}/mcp-surface-bindings`,
  );
}

export function createExpertMcpSurfaceBinding(
  expertId: string,
  input: McpSurfaceBindingCreateInput,
) {
  return apiRequest<McpSurfaceBinding>(
    `/api/experts/${encodeURIComponent(expertId)}/mcp-surface-bindings`,
    { method: 'POST', json: input },
  );
}

export function revokeExpertMcpSurfaceBinding(
  expertId: string,
  bindingId: string,
) {
  return apiRequest<void>(
    `/api/experts/${encodeURIComponent(expertId)}/mcp-surface-bindings/${encodeURIComponent(bindingId)}`,
    { method: 'DELETE' },
  );
}

export function listMcpExternalApprovals(params?: {
  limit?: number;
  offset?: number;
}) {
  return apiRequest<McpExternalApprovalList>(
    `/api/apps/mcp/external-approvals${paging(params)}`,
  );
}

export function decideMcpExternalApproval(
  approvalId: string,
  decision: 'approve' | 'deny',
) {
  return apiRequest<McpExternalApproval>(
    `/api/apps/mcp/external-approvals/${encodeURIComponent(approvalId)}`,
    { method: 'POST', json: { decision } },
  );
}

export function listMcpExternalDeliveries(
  params: { status?: string; limit?: number; offset?: number } = {},
) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset !== undefined) query.set('offset', String(params.offset));
  const suffix = query.toString() ? `?${query}` : '';
  return apiRequest<McpExternalDeliveryList>(
    `/api/apps/mcp/external-deliveries${suffix}`,
  );
}

export function reconcileMcpExternalDelivery(
  deliveryId: string,
  resolution: 'confirmed_sent' | 'cancelled',
) {
  return apiRequest<McpExternalDelivery>(
    `/api/apps/mcp/external-deliveries/${encodeURIComponent(deliveryId)}/reconcile`,
    { method: 'POST', json: { resolution } },
  );
}

export function decideConversationToolApproval(
  conversationId: string,
  approvalId: string,
  decision: 'approve' | 'deny',
) {
  return apiRequest<{ id: string; status: string }>(
    `/api/conversations/${encodeURIComponent(conversationId)}/tool-approvals/${encodeURIComponent(approvalId)}`,
    { method: 'POST', json: { decision } },
  );
}
