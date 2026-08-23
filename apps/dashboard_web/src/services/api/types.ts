export type User = {
  id: string;
  email: string;
  status: string;
  platform_role: string;
  created_at: string;
  email_verified_at?: string | null;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
};

export type PlatformMeResponse = {
  user: User;
  platform_role: string;
  authorized: boolean;
};

export const PLATFORM_ROLE_ADMIN = 'admin';

export function isPlatformAdmin(user: Pick<User, 'platform_role'> | null | undefined): boolean {
  return user?.platform_role === PLATFORM_ROLE_ADMIN;
}

export type PlatformPageParams = {
  limit?: number;
  offset?: number;
  search?: string;
  status?: string;
  kind?: string;
  platform_role?: string;
  currency?: string;
  gateway?: string;
  workspace_id?: string;
  created_from?: string;
  created_to?: string;
};

/** Canonical Workspace Geem entitlement keys (catalog-driven; do not hardcode by plan name). */
export type PlatformEntitlementKey =
  | 'ai_tokens_daily'
  | 'ai_tokens_weekly'
  | 'ai_tokens_monthly'
  | 'experts_limit'
  | 'storage_bytes'
  | 'api_requests_per_minute';

export type PlatformWorkspaceListItem = {
  id: string;
  name: string;
  slug: string;
  kind: string;
  status: string;
  created_at: string;
  updated_at: string;
  created_by?: string | null;
  deleted_at?: string | null;
  members_count: number;
  experts_count: number;
  current_plan_code?: string | null;
  current_plan_name?: string | null;
  subscription_status?: string | null;
};

export type PlatformWorkspaceListResponse = {
  items: PlatformWorkspaceListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformWorkspaceOwner = {
  user_id: string;
  email: string;
  status: string;
  membership_id: string;
  role_id: string;
  role_name: string;
};

export type PlatformSubscriptionSummary = {
  subscription_id: string;
  status: string;
  plan_id: string;
  plan_code: string;
  plan_name: string;
  starts_at: string;
  current_period_start: string;
  current_period_end: string;
  ends_at?: string | null;
};

export type PlatformResourceSummary = {
  members_count: number;
  experts_count: number;
  api_keys_count: number;
  app_installations_count: number;
  storage_used_bytes?: number | null;
  storage_limit_bytes?: number | null;
};

export type PlatformWorkspaceDetail = {
  id: string;
  name: string;
  slug: string;
  kind: string;
  status: string;
  created_at: string;
  updated_at: string;
  created_by?: string | null;
  deleted_at?: string | null;
  purged_at?: string | null;
  members_count: number;
  owners: PlatformWorkspaceOwner[];
  subscription: PlatformSubscriptionSummary | null;
  resources: PlatformResourceSummary;
};

export type PlatformWorkspaceMember = {
  membership_id: string;
  user_id: string;
  email: string;
  user_status: string;
  role_id: string;
  role_name: string;
  is_owner_role: boolean;
  created_at: string;
};

export type PlatformWorkspaceMembersResponse = {
  items: PlatformWorkspaceMember[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformUserListItem = {
  id: string;
  email: string;
  status: string;
  platform_role: string;
  created_at: string;
  email_verified_at?: string | null;
  last_login_at?: string | null;
  workspace_memberships_count: number;
};

export type PlatformUserListResponse = {
  items: PlatformUserListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformUserMembership = {
  membership_id: string;
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  workspace_status: string;
  role_id: string;
  role_name: string;
  is_owner_role: boolean;
  created_at: string;
};

export type PlatformUserDetail = {
  id: string;
  email: string;
  status: string;
  platform_role: string;
  created_at: string;
  updated_at: string;
  email_verified_at?: string | null;
  deleted_at?: string | null;
  last_login_at?: string | null;
  active_session_count: number;
  memberships: PlatformUserMembership[];
};

// --- Phase 12C: Plans & Workspace billing ---

export type PlatformPlanEntitlement = {
  key: string;
  value: number | boolean | string;
  value_type: string;
};

export type PlatformPlanListItem = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  status: string;
  price_amount: string | null;
  currency: string;
  is_bootstrap: boolean;
  is_commercial: boolean;
  subscriber_count: number;
  entitlements: PlatformPlanEntitlement[];
  created_at: string;
  updated_at: string;
};

export type PlatformPlanListResponse = {
  items: PlatformPlanListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformPlanDetail = PlatformPlanListItem;

export type PlatformPlanEntitlementInput = {
  key: string;
  value: number;
};

export type PlatformPlanCreateBody = {
  code: string;
  name: string;
  description?: string | null;
  price_amount?: string | null;
  currency: string;
  entitlements: PlatformPlanEntitlementInput[];
};

export type PlatformPlanUpdateBody = {
  name?: string;
  description?: string | null;
  price_amount?: string | null;
  clear_price?: boolean;
  currency?: string;
  entitlements?: PlatformPlanEntitlementInput[];
  reason?: string | null;
};

export type PlatformEntitlementCatalogItem = {
  key: string;
  value_type: string;
  unit: string;
};

export type PlatformEntitlementCatalogResponse = {
  items: PlatformEntitlementCatalogItem[];
};

export type PlatformSubscriptionDetail = {
  subscription_id: string;
  status: string;
  plan_id: string;
  plan_code: string;
  plan_name: string;
  plan_status: string;
  starts_at: string;
  current_period_start: string;
  current_period_end: string;
  ends_at?: string | null;
  source?: string | null;
  created_at: string;
};

export type PlatformSubscriptionHistoryItem = {
  subscription_id: string;
  status: string;
  plan_id: string;
  plan_code: string;
  plan_name: string;
  starts_at: string;
  current_period_start: string;
  current_period_end: string;
  ends_at?: string | null;
  source?: string | null;
  created_at: string;
};

export type PlatformSubscriptionHistoryResponse = {
  items: PlatformSubscriptionHistoryItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformSubscriptionAssignBody = {
  plan_id: string;
  reason: string;
};

export type PlatformEntitlementItem = {
  key: string;
  value: number | boolean | string;
  value_type: string;
};

export type PlatformWorkspaceEntitlements = {
  workspace_id: string;
  subscription_id: string;
  plan_id: string;
  plan_code: string;
  plan_name: string;
  plan_status: string;
  items: PlatformEntitlementItem[];
};

export type PlatformUsageMeter = {
  limit: number;
  used: number;
  reserved?: number;
  remaining?: number;
  period_start?: string | null;
  period_end?: string | null;
};

export type PlatformWorkspaceUsage = {
  ai_tokens_daily: PlatformUsageMeter;
  ai_tokens_weekly: PlatformUsageMeter;
  ai_tokens_monthly: PlatformUsageMeter;
  experts: PlatformUsageMeter;
  storage_bytes: PlatformUsageMeter;
  credit_balance: number;
};

export type PlatformCreditLedgerItem = {
  id: string;
  entry_type: string;
  amount: number;
  remaining_amount?: number | null;
  request_id?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  reason?: string | null;
  created_at: string;
};

export type PlatformWorkspaceCredits = {
  workspace_id: string;
  balance: number;
  recent: PlatformCreditLedgerItem[];
};

export type PlatformCreditHistoryResponse = {
  items: PlatformCreditLedgerItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformCreditGrantBody = {
  amount: number;
  reason: string;
  request_id?: string;
};

export type PlatformCreditGrantResponse = {
  workspace_id: string;
  balance: number;
  entry: PlatformCreditLedgerItem;
  idempotent_replay: boolean;
};

// --- Phase 12D: Platform Experts ---

export type ExpertRagConfig = {
  top_k?: number;
  rerank_top_n?: number;
  similarity_threshold?: number;
};

export type PlatformExpertListItem = {
  id: string;
  type: string;
  ownership: string;
  workspace_id: string | null;
  name: string;
  description: string | null;
  icon_url: string | null;
  status: string;
  visibility: string;
  availability_mode: string;
  knowledge_mode: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  knowledge_document_count: number;
  explicit_workspace_grant_count: number;
  is_protected: boolean;
};

export type PlatformExpertDetail = PlatformExpertListItem & {
  system_instructions: string | null;
  rag_config: ExpertRagConfig | null;
};

export type PlatformExpertListResponse = {
  items: PlatformExpertListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformExpertWorkspaceGrant = {
  id: string;
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  workspace_status: string;
  expert_id: string;
  created_by: string | null;
  created_at: string;
};

export type PlatformExpertGrantListResponse = {
  items: PlatformExpertWorkspaceGrant[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformExpertKnowledgeItem = {
  id: string;
  expert_id: string;
  document_id: string | null;
  source_id: string | null;
  created_at: string;
  title: string;
  original_filename: string;
  status: string;
  mime_type: string | null;
  byte_size: number | null;
  page_count: number;
  failure_reason: string | null;
  source_type: string;
  processed_pages: number;
  failed_pages: number;
  current_stage: string | null;
  progress: number;
};

export type PlatformExpertKnowledgeListResponse = {
  items: PlatformExpertKnowledgeItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformExpertCreateBody = {
  name: string;
  description?: string | null;
  system_instructions?: string | null;
  rag_config?: ExpertRagConfig | null;
  visibility?: string | null;
  status?: string | null;
  availability_mode?: string | null;
  icon_url?: string | null;
};

export type PlatformExpertUpdateBody = Partial<PlatformExpertCreateBody>;

export type PlatformExpertUploadResponse = {
  expert_id: string;
  source_id: string;
  document_id: string;
  status: string;
  mime_type: string;
  page_count: number;
  reused: boolean;
};

export type PlatformExpertPageParams = PlatformPageParams & {
  visibility?: string;
  knowledge_mode?: string;
  availability_mode?: string;
  published?: boolean;
};

// --- Phase 12E: Platform App Store ---

export type PlatformAppCategory = {
  id: string;
  slug: string;
  name_key: string;
  description_key?: string | null;
  icon?: string | null;
  sort_order: number;
  is_active: boolean;
};

export type PlatformAppCategoryListResponse = {
  items: PlatformAppCategory[];
};

export type PlatformAppCategoryUpdateBody = {
  is_active?: boolean | null;
  sort_order?: number | null;
};

export type PlatformAppEntitlementCatalogItem = {
  key: string;
  value_type: string;
  unit: string;
};

export type PlatformAppEntitlementCatalogResponse = {
  items: PlatformAppEntitlementCatalogItem[];
};

export type PlatformAppPlanEntitlement = {
  key: string;
  value: number | boolean | string;
};

export type PlatformAppPlanEntitlementInput = {
  key: string;
  value: number;
};

export type PlatformAppPlanListItem = {
  id: string;
  app_id: string;
  code: string;
  name: string;
  description?: string | null;
  billing_interval: string;
  price_amount: string;
  currency: string;
  is_default: boolean;
  is_active: boolean;
  active_entitlement_count: number;
  entitlements: PlatformAppPlanEntitlement[];
  created_at: string;
  updated_at: string;
};

export type PlatformAppPlanListResponse = {
  items: PlatformAppPlanListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformAppPlanDetail = PlatformAppPlanListItem;

export type PlatformAppPlanCreateBody = {
  code: string;
  name: string;
  description?: string | null;
  price_amount?: string;
  currency?: string;
  billing_interval?: string;
  is_default?: boolean;
  entitlements?: PlatformAppPlanEntitlementInput[];
};

export type PlatformAppPlanUpdateBody = {
  code?: string;
  name?: string;
  description?: string | null;
  price_amount?: string;
  currency?: string;
  billing_interval?: string;
  is_default?: boolean;
  is_active?: boolean;
  entitlements?: PlatformAppPlanEntitlementInput[];
  reason?: string | null;
};

export type PlatformAppListItem = {
  id: string;
  slug: string;
  name: string;
  short_description: string;
  category_slug: string;
  category_name_key: string;
  billing_type: string;
  status: string;
  icon_url?: string | null;
  connector_key?: string | null;
  connector_kind?: string | null;
  plans_count: number;
  installations_count: number;
  active_entitlements_count: number;
  created_at: string;
  updated_at: string;
};

export type PlatformAppListResponse = {
  items: PlatformAppListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformAppDetail = {
  id: string;
  slug: string;
  name: string;
  short_description: string;
  description?: string | null;
  category_id: string;
  category_slug: string;
  category_name_key: string;
  billing_type: string;
  status: string;
  is_featured: boolean;
  icon_url?: string | null;
  connector_key?: string | null;
  connector_kind?: string | null;
  sort_order: number;
  slug_locked: boolean;
  billing_type_locked: boolean;
  connector_locked: boolean;
  is_seeded: boolean;
  disable_allowed: boolean;
  plans: PlatformAppPlanListItem[];
  installations_count: number;
  active_licenses_count: number;
  active_subscriptions_count: number;
  created_at: string;
  updated_at: string;
};

export type PlatformAppCreateBody = {
  slug: string;
  name: string;
  short_description: string;
  description?: string | null;
  category_id: string;
  billing_type?: string;
  icon_url?: string | null;
  connector_key?: string | null;
  connector_kind?: string | null;
  is_featured?: boolean;
  sort_order?: number;
};

export type PlatformAppUpdateBody = {
  name?: string;
  slug?: string;
  short_description?: string;
  description?: string | null;
  category_id?: string;
  billing_type?: string;
  icon_url?: string | null;
  connector_key?: string | null;
  connector_kind?: string | null;
  is_featured?: boolean;
  sort_order?: number;
};

export type PlatformAppLifecycleBody = {
  reason: string;
};

export type PlatformAppWorkspaceEntitlement = {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  access_status: string;
  installed: boolean;
  plan_id?: string | null;
  plan_code?: string | null;
  plan_name?: string | null;
  license_status?: string | null;
  license_source?: string | null;
  subscription_status?: string | null;
  subscription_source?: string | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
  entitlements: Record<string, unknown>;
};

export type PlatformAppWorkspaceEntitlementListResponse = {
  items: PlatformAppWorkspaceEntitlement[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformWorkspaceApp = {
  app_id: string;
  app_slug: string;
  app_name: string;
  billing_type: string;
  catalog_status: string;
  access_status: string;
  installed: boolean;
  installation_status?: string | null;
  plan_id?: string | null;
  plan_code?: string | null;
  plan_name?: string | null;
  license_status?: string | null;
  license_source?: string | null;
  subscription_status?: string | null;
  subscription_source?: string | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
  entitlements: Record<string, unknown>;
  connections_used?: number | null;
  connections_limit?: number | null;
  widgets_used?: number | null;
  widgets_limit?: number | null;
};

export type PlatformWorkspaceAppsResponse = {
  items: PlatformWorkspaceApp[];
};

export type PlatformAppLicenseGrantBody = {
  app_plan_id: string;
  reason: string;
  idempotency_key?: string;
};

export type PlatformAppLicenseRevokeBody = {
  reason: string;
};

export type PlatformAppSubscriptionGrantBody = {
  app_plan_id: string;
  reason: string;
  idempotency_key?: string;
};

export type PlatformAppSubscriptionExtendBody = {
  reason: string;
  idempotency_key?: string;
};

export type PlatformAppSubscriptionRevokeBody = {
  reason: string;
};

export type PlatformAppCommercialGrantResponse = {
  workspace_id: string;
  app_id: string;
  license_id?: string | null;
  subscription_id?: string | null;
  access_status: string;
  idempotent_replay: boolean;
};

export type PlatformAppPageParams = PlatformPageParams & {
  billing_type?: string;
  category?: string;
  connector_kind?: string;
};

// --- Phase 12F: Payment gateways ---

export type PlatformGatewayCredentialStatus = {
  profile_id_configured?: boolean | null;
  server_key_configured?: boolean | null;
  profile_id?: string | null;
};

export type PlatformPaymentGatewayListItem = {
  id: string | null;
  code: string;
  display_name: string;
  enabled: boolean;
  test_mode: boolean | null;
  configured: boolean;
  credential_field_status: PlatformGatewayCredentialStatus;
  created_at: string | null;
  updated_at: string | null;
  referenced_purchases_count: number;
  in_flight_purchases_count: number;
};

export type PlatformPaymentGatewayListResponse = {
  items: PlatformPaymentGatewayListItem[];
  active_gateway_id: string | null;
};

export type PlatformPaymentGatewayDetail = PlatformPaymentGatewayListItem & {
  id: string;
  credentials: PlatformGatewayCredentialStatus;
};

export type PlatformPaymentGatewayCreateBody = {
  code: string;
  test_mode?: boolean;
  credentials?: Record<string, string>;
};

export type PlatformPaymentGatewayUpdateBody = {
  test_mode?: boolean;
  credentials?: Record<string, string>;
  profile_id?: string;
};

// --- Phase 12F: Purchases ---

export type PlatformPurchaseWorkspace = {
  id: string;
  name: string;
  slug: string;
};

export type PlatformPurchaseActor = {
  id: string;
  email: string;
};

export type PlatformPurchaseTarget = {
  kind: string;
  item_name?: string | null;
  item_code?: string | null;
  credits?: number | null;
  app_id?: string | null;
  app_slug?: string | null;
  app_name?: string | null;
};

export type PlatformPurchaseListItem = {
  id: string;
  workspace: PlatformPurchaseWorkspace;
  actor: PlatformPurchaseActor;
  kind: string;
  status: string;
  amount: string;
  currency: string;
  gateway_code: string;
  gateway_config_id: string;
  cart_id: string;
  tran_ref?: string | null;
  target: PlatformPurchaseTarget;
  paid_at?: string | null;
  created_at: string;
  updated_at: string;
  reconcile_eligible: boolean;
  invoice_available: boolean;
};

export type PlatformPurchaseListResponse = {
  items: PlatformPurchaseListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformPurchaseFulfillment = {
  fulfilled: boolean;
  invoice_available: boolean;
  invoice_number?: string | null;
};

export type PlatformPurchaseGateway = {
  code: string;
  display_name: string;
  gateway_config_id: string;
  cart_id: string;
  tran_ref?: string | null;
  provider_status?: string | null;
  last_query_status?: string | null;
};

export type PlatformPurchaseDetail = {
  id: string;
  workspace: PlatformPurchaseWorkspace;
  actor: PlatformPurchaseActor;
  kind: string;
  status: string;
  amount: string;
  currency: string;
  target: PlatformPurchaseTarget;
  gateway: PlatformPurchaseGateway;
  fulfillment: PlatformPurchaseFulfillment;
  paid_at?: string | null;
  created_at: string;
  updated_at: string;
  reconcile_eligible: boolean;
};

export type PlatformPurchaseReconcileResponse = {
  purchase: PlatformPurchaseDetail;
  prior_status: string;
  resulting_status: string;
  fulfillment_applied: boolean;
  provider_status?: string | null;
  idempotent_replay: boolean;
};

export type PlatformPurchasePageParams = PlatformPageParams & {
  gateway?: string;
  created_from?: string;
  created_to?: string;
  workspace_id?: string;
};

// --- Phase 12G: Dashboard / Usage / Audit ---

export type PlatformAuditActor = {
  user_id?: string | null;
  api_key_id?: string | null;
  email?: string | null;
};

export type PlatformAuditWorkspace = {
  workspace_id: string;
  name: string;
  slug: string;
};

export type PlatformAuditResource = {
  entity_type: string;
  entity_id?: string | null;
};

export type PlatformAuditListItem = {
  id: string;
  created_at: string;
  actor?: PlatformAuditActor | null;
  workspace?: PlatformAuditWorkspace | null;
  action: string;
  resource: PlatformAuditResource;
  request_id?: string | null;
  summary?: string | null;
};

export type PlatformAuditListResponse = {
  items: PlatformAuditListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type PlatformAuditLogDetail = PlatformAuditListItem & {
  metadata: Record<string, unknown>;
};

export type PlatformDashboardSummary = {
  workspaces: { total: number; active: number; disabled: number };
  users: { total: number; active: number; disabled: number };
  experts: { published: number; draft: number };
  usage: {
    billed_tokens_24h: number;
    billed_tokens_7d: number;
    billed_tokens_30d: number;
    active_workspaces_30d: number;
    outstanding_credit_balance: number;
  };
  billing: {
    active_subscriptions: number;
    pending_purchases: number;
    failed_purchases_30d: number;
    paid_purchase_count_30d: number;
    paid_purchase_volume_30d: string;
  };
  apps: {
    published: number;
    active_subscriptions: number;
    active_licenses: number;
    installations: number;
  };
  gateway?: {
    gateway_config_id: string;
    code: string;
    enabled: boolean;
    test_mode: boolean;
  } | null;
  recent_activity: PlatformAuditListItem[];
};

export type PlatformUsageDateParams = {
  from?: string;
  to?: string;
};

export type PlatformUsageSummary = {
  from_day: string;
  to_day: string;
  total_billed_tokens: number;
  active_workspaces: number;
  average_daily_billed_tokens: number;
  peak_day?: { day: string; billed_tokens: number } | null;
  families: { family: string; billed_tokens: number; percentage: number }[];
  sources: { source: string; billed_tokens: number; percentage: number }[];
};

export type PlatformUsageTrendPoint = {
  date: string;
  billed_tokens: number;
  active_workspaces: number;
};

export type PlatformUsageTrendResponse = {
  from_day: string;
  to_day: string;
  points: PlatformUsageTrendPoint[];
};

export type PlatformUsageWorkspaceItem = {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  workspace_status: string;
  billed_tokens: number;
  percentage_of_platform_usage: number;
  active_days: number;
  current_plan_code?: string | null;
  current_plan_name?: string | null;
};

export type PlatformUsageWorkspacesResponse = {
  items: PlatformUsageWorkspaceItem[];
  total: number;
  limit: number;
  offset: number;
  from_day: string;
  to_day: string;
  platform_total_billed_tokens: number;
};

export type PlatformUsageEventItem = {
  id: string;
  created_at: string;
  workspace_id?: string | null;
  workspace_name?: string | null;
  workspace_slug?: string | null;
  user_id?: string | null;
  expert_id?: string | null;
  api_key_id?: string | null;
  family: string;
  operation_type: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  billed_tokens: number;
  cost_metadata: Record<string, unknown>;
};

export type PlatformUsageEventsResponse = {
  items: PlatformUsageEventItem[];
  total: number;
  limit: number;
  offset: number;
  from_day: string;
  to_day: string;
};

export type PlatformWorkspaceUsageSummary = {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  workspace_status: string;
  workspace_kind: string;
  from_day: string;
  to_day: string;
  total_billed_tokens: number;
  families: PlatformUsageSummary['families'];
  sources: PlatformUsageSummary['sources'];
};

export type PlatformWorkspaceUsageTrendResponse = {
  workspace_id: string;
  from_day: string;
  to_day: string;
  points: PlatformUsageTrendPoint[];
};

export type PlatformUsagePageParams = PlatformUsageDateParams &
  PlatformPageParams & {
    family?: string;
    operation_type?: string;
    api_key_id?: string;
    sort?: string;
  };

export type PlatformAuditPageParams = PlatformPageParams & {
  actor_user_id?: string;
  workspace_id?: string;
  action?: string;
  entity_type?: string;
  entity_id?: string;
  from?: string;
  to?: string;
  scope?: string;
};
