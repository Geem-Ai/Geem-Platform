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
