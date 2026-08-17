import { apiRequest } from './client';
import type { CheckoutResult } from './billing';

export type AppBillingType = 'free' | 'one_time' | 'subscription';
export type AppStatus = 'draft' | 'published' | 'coming_soon' | 'disabled';
export type AppAccessRequirement = 'free' | 'one_time' | 'subscription' | 'unavailable';

export type AppAccessStatus =
  | 'not_entitled'
  | 'entitled_not_installed'
  | 'active'
  | 'expired'
  | 'unavailable';

export type AppCategory = {
  slug: string;
  name_key: string;
  description_key: string | null;
  icon: string | null;
  sort_order: number;
};

export type AppPlan = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  billing_interval: 'none' | 'monthly' | string;
  price_amount: string;
  currency: string;
  is_default: boolean;
  entitlements: Record<string, unknown>;
};

export type AppInstallationSummary = {
  id: string | null;
  status: string | null;
  installed_at: string | null;
};

export type AppAccess = {
  status: AppAccessStatus;
  plan_id: string | null;
  plan_code: string | null;
  plan_name: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  commercially_entitled: boolean;
  can_purchase: boolean;
  can_renew: boolean;
  can_install: boolean;
  can_uninstall: boolean;
};

export type CatalogApp = {
  id: string;
  slug: string;
  name: string;
  short_description: string;
  description: string | null;
  category: AppCategory;
  icon_url: string | null;
  billing_type: AppBillingType;
  status: AppStatus;
  is_featured: boolean;
  sort_order: number;
  plans: AppPlan[];
  installation: AppInstallationSummary | null;
  installation_status: string | null;
  can_install: boolean;
  can_uninstall: boolean;
  access_requirement: AppAccessRequirement;
  access: AppAccess | null;
  connector: ConnectorCapability | null;
  has_active_connection: boolean;
  /** Summary status of the workspace's primary connection for this app, if any. */
  connection_status?: ConnectionStatus | string | null;
};

export type ConnectorCapability = {
  key: string;
  kind: string | null;
  available: boolean;
  auth_mode: string | null;
  can_connect: boolean;
  supports_sync: boolean;
  supports_webhooks: boolean;
  supports_health_check: boolean;
  unavailable_reason?: string | null;
};

export type ConnectionStatus =
  | 'pending'
  | 'connecting'
  | 'active'
  | 'degraded'
  | 'error'
  | 'disconnected'
  | 'revoked';

export type ConnectionHealth = 'unknown' | 'healthy' | 'degraded' | 'failed';

export type ConnectionCapabilities = {
  can_disconnect: boolean;
  can_health_check: boolean;
  can_sync: boolean;
  can_reconnect: boolean;
};

export type AppConnection = {
  id: string;
  workspace_id: string;
  app_installation_id: string;
  app_slug: string;
  connector_key: string;
  connector_kind: string | null;
  display_name: string | null;
  external_account_id: string | null;
  external_account_name: string | null;
  auth_mode: string;
  status: ConnectionStatus | string;
  health: ConnectionHealth | string;
  connected_at: string | null;
  disconnected_at: string | null;
  last_health_check_at: string | null;
  last_success_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  last_error_at: string | null;
  credentials_expires_at: string | null;
  created_at: string | null;
  capabilities: ConnectionCapabilities;
  /** Present when starting an OAuth connection — navigate the browser here. */
  authorization_url?: string | null;
};

export type AppConnectionList = {
  items: AppConnection[];
  total: number;
  limit: number;
  offset: number;
};

export type SyncTrigger =
  | 'initial'
  | 'manual'
  | 'scheduled'
  | 'webhook'
  | 'reconcile';

export type SyncRunStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'partial'
  | 'failed'
  | 'cancelled';

export type ConnectorSyncRun = {
  id: string;
  workspace_id: string;
  app_connection_id: string;
  trigger: SyncTrigger | string;
  status: SyncRunStatus | string;
  started_at: string | null;
  completed_at: string | null;
  items_seen: number;
  items_created: number;
  items_updated: number;
  items_deleted: number;
  items_failed: number;
  error_code: string | null;
  error_message: string | null;
  created_by_user_id: string | null;
  created_at: string | null;
};

export type ConnectorSyncRunList = {
  items: ConnectorSyncRun[];
  total: number;
  limit: number;
  offset: number;
};

export type CatalogAppList = {
  items: CatalogApp[];
  total: number;
  limit: number;
  offset: number;
};

export type AppInstallation = {
  id: string;
  workspace_id: string;
  app_id: string;
  status: string;
  installed_at: string;
  uninstalled_at: string | null;
  installed_by_user_id: string | null;
  app: CatalogApp;
};

export type AppInstallationList = {
  items: AppInstallation[];
  total: number;
  limit: number;
  offset: number;
};

export type ListAppsParams = {
  category?: string;
  billing_type?: string;
  installed?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
};

function toQuery(params?: ListAppsParams): string {
  if (!params) return '';
  const q = new URLSearchParams();
  if (params.category) q.set('category', params.category);
  if (params.billing_type) q.set('billing_type', params.billing_type);
  if (params.installed !== undefined) q.set('installed', String(params.installed));
  if (params.q) q.set('q', params.q);
  if (params.limit !== undefined) q.set('limit', String(params.limit));
  if (params.offset !== undefined) q.set('offset', String(params.offset));
  const s = q.toString();
  return s ? `?${s}` : '';
}

export async function listAppCategories(): Promise<AppCategory[]> {
  return apiRequest<AppCategory[]>('/api/apps/categories');
}

export async function listApps(params?: ListAppsParams): Promise<CatalogAppList> {
  return apiRequest<CatalogAppList>(`/api/apps${toQuery(params)}`);
}

export async function getApp(slug: string): Promise<CatalogApp> {
  return apiRequest<CatalogApp>(`/api/apps/${encodeURIComponent(slug)}`);
}

export async function listAppInstallations(params?: {
  limit?: number;
  offset?: number;
}): Promise<AppInstallationList> {
  const q = new URLSearchParams();
  if (params?.limit !== undefined) q.set('limit', String(params.limit));
  if (params?.offset !== undefined) q.set('offset', String(params.offset));
  const s = q.toString();
  return apiRequest<AppInstallationList>(
    `/api/apps/installations${s ? `?${s}` : ''}`,
  );
}

export async function getAppInstallation(
  installationId: string,
): Promise<AppInstallation> {
  return apiRequest<AppInstallation>(
    `/api/apps/installations/${encodeURIComponent(installationId)}`,
  );
}

export async function installApp(slug: string): Promise<AppInstallation> {
  return apiRequest<AppInstallation>(
    `/api/apps/${encodeURIComponent(slug)}/install`,
    { method: 'POST' },
  );
}

export async function uninstallApp(slug: string): Promise<AppInstallation> {
  return apiRequest<AppInstallation>(
    `/api/apps/${encodeURIComponent(slug)}/install`,
    { method: 'DELETE' },
  );
}

export async function createAppCheckout(
  slug: string,
  planId: string,
): Promise<CheckoutResult> {
  return apiRequest<CheckoutResult>(
    `/api/apps/${encodeURIComponent(slug)}/checkout`,
    { method: 'POST', json: { plan_id: planId } },
  );
}

export async function createAppRenewal(slug: string): Promise<CheckoutResult> {
  return apiRequest<CheckoutResult>(
    `/api/apps/${encodeURIComponent(slug)}/renew`,
    { method: 'POST', json: {} },
  );
}

export async function listAppConnections(
  slug: string,
  params?: { limit?: number; offset?: number },
): Promise<AppConnectionList> {
  const q = new URLSearchParams();
  if (params?.limit !== undefined) q.set('limit', String(params.limit));
  if (params?.offset !== undefined) q.set('offset', String(params.offset));
  const s = q.toString();
  return apiRequest<AppConnectionList>(
    `/api/apps/${encodeURIComponent(slug)}/connections${s ? `?${s}` : ''}`,
  );
}

export async function startAppConnection(
  slug: string,
  body?: {
    display_name?: string;
    connection_id?: string;
    return_path?: string;
  },
): Promise<AppConnection> {
  return apiRequest<AppConnection>(
    `/api/apps/${encodeURIComponent(slug)}/connections`,
    {
      method: 'POST',
      json: {
        display_name: body?.display_name ?? null,
        connection_id: body?.connection_id ?? null,
        return_path: body?.return_path ?? null,
      },
    },
  );
}

export type GoogleDrivePickerSession = {
  access_token: string;
  expires_at: string | null;
  app_id: string | null;
  developer_key: string | null;
};

/** Short-lived Picker token — keep memory-only; never persist. */
export async function createGoogleDrivePickerSession(
  connectionId: string,
): Promise<GoogleDrivePickerSession> {
  return apiRequest<GoogleDrivePickerSession>(
    `/api/apps/google-drive/connections/${encodeURIComponent(connectionId)}/picker-session`,
    { method: 'POST' },
  );
}

export type MicrosoftOneDrivePickerSession = {
  access_token: string;
  expires_at: string | null;
  base_url: string;
  client_id: string | null;
  tenant: string | null;
  drive_id: string | null;
  account_kind?: 'personal' | 'work_school';
  picker_mode?: string | null;
};

export type MicrosoftOneDrivePickerToken = {
  access_token: string;
  expires_at: string | null;
  resource: string;
};

/** File Picker v8 bootstrap — tokens are memory-only. */
export async function createMicrosoftOneDrivePickerSession(
  connectionId: string,
): Promise<MicrosoftOneDrivePickerSession> {
  return apiRequest<MicrosoftOneDrivePickerSession>(
    `/api/apps/microsoft-onedrive/connections/${encodeURIComponent(connectionId)}/picker-session`,
    { method: 'POST' },
  );
}

/** Short-lived SharePoint-resource token for Picker authenticate commands. */
export async function createMicrosoftOneDrivePickerToken(
  connectionId: string,
  body: { resource: string },
): Promise<MicrosoftOneDrivePickerToken> {
  return apiRequest<MicrosoftOneDrivePickerToken>(
    `/api/apps/microsoft-onedrive/connections/${encodeURIComponent(connectionId)}/picker-token`,
    {
      method: 'POST',
      json: { resource: body.resource },
    },
  );
}

export async function getAppConnection(
  slug: string,
  connectionId: string,
): Promise<AppConnection> {
  return apiRequest<AppConnection>(
    `/api/apps/${encodeURIComponent(slug)}/connections/${encodeURIComponent(connectionId)}`,
  );
}

export async function disconnectAppConnection(
  slug: string,
  connectionId: string,
): Promise<AppConnection> {
  return apiRequest<AppConnection>(
    `/api/apps/${encodeURIComponent(slug)}/connections/${encodeURIComponent(connectionId)}`,
    { method: 'DELETE' },
  );
}

export async function healthCheckAppConnection(
  slug: string,
  connectionId: string,
): Promise<AppConnection> {
  return apiRequest<AppConnection>(
    `/api/apps/${encodeURIComponent(slug)}/connections/${encodeURIComponent(connectionId)}/health-check`,
    { method: 'POST' },
  );
}

export async function requestAppConnectionSync(
  slug: string,
  connectionId: string,
  idempotencyKey?: string,
): Promise<ConnectorSyncRun> {
  return apiRequest<ConnectorSyncRun>(
    `/api/apps/${encodeURIComponent(slug)}/connections/${encodeURIComponent(connectionId)}/sync`,
    {
      method: 'POST',
      json: idempotencyKey ? { idempotency_key: idempotencyKey } : {},
    },
  );
}

export async function listConnectionSyncRuns(
  slug: string,
  connectionId: string,
  params?: { limit?: number; offset?: number },
): Promise<ConnectorSyncRunList> {
  const q = new URLSearchParams();
  if (params?.limit !== undefined) q.set('limit', String(params.limit));
  if (params?.offset !== undefined) q.set('offset', String(params.offset));
  const s = q.toString();
  return apiRequest<ConnectorSyncRunList>(
    `/api/apps/${encodeURIComponent(slug)}/connections/${encodeURIComponent(connectionId)}/sync-runs${s ? `?${s}` : ''}`,
  );
}
