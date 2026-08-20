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
};

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
