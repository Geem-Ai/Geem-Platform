/** Geem workspace permission keys. Must stay aligned with backend WorkspacePermission. */

export const WorkspacePermission = {
  WORKSPACE_VIEW: 'workspace.view',
  WORKSPACE_DELETE: 'workspace.delete',
  WORKSPACE_SETTINGS_VIEW: 'workspace_settings.view',
  WORKSPACE_SETTINGS_MANAGE: 'workspace_settings.manage',
  CHAT_USE: 'chat.use',
  EXPERTS_VIEW: 'experts.view',
  EXPERTS_USE: 'experts.use',
  EXPERTS_CREATE: 'experts.create',
  EXPERTS_UPDATE: 'experts.update',
  EXPERTS_DELETE: 'experts.delete',
  EXPERTS_MANAGE_KNOWLEDGE: 'experts.manage_knowledge',
  STORAGE_VIEW: 'storage.view',
  STORAGE_DOWNLOAD: 'storage.download',
  STORAGE_UPLOAD: 'storage.upload',
  STORAGE_UPDATE: 'storage.update',
  STORAGE_DELETE: 'storage.delete',
  STORAGE_REPROCESS: 'storage.reprocess',
  APPS_VIEW: 'apps.view',
  APPS_MANAGE: 'apps.manage',
  APPS_CONNECT: 'apps.connect',
  MCP_TOOLS_APPROVE_EXTERNAL: 'mcp_tools.approve_external',
  MEMBERS_VIEW: 'members.view',
  MEMBERS_INVITE: 'members.invite',
  MEMBERS_UPDATE_ROLE: 'members.update_role',
  MEMBERS_REMOVE: 'members.remove',
  MEMBERS_PROMOTE_OWNER: 'members.promote_owner',
  ROLES_VIEW: 'roles.view',
  ROLES_MANAGE: 'roles.manage',
  API_KEYS_VIEW: 'api_keys.view',
  API_KEYS_CREATE: 'api_keys.create',
  API_KEYS_REVOKE: 'api_keys.revoke',
  API_USAGE_VIEW: 'api_usage.view',
  BILLING_VIEW: 'billing.view',
  BILLING_MANAGE: 'billing.manage',
  BILLING_PURCHASE_CREDITS: 'billing.purchase_credits',
} as const;

export type WorkspacePermissionKey =
  (typeof WorkspacePermission)[keyof typeof WorkspacePermission];

export const ALL_PERMISSION_KEYS: readonly WorkspacePermissionKey[] =
  Object.values(WorkspacePermission);

/** i18n key for a permission UX label (`permissions.<key>.name`). */
export function permissionLabelKey(permission: string): string {
  return `permissions.${permission}.name`;
}

/** i18n key for a permission UX description (`permissions.<key>.description`). */
export function permissionDescriptionKey(permission: string): string {
  return `permissions.${permission}.description`;
}

export function permissionSet(
  keys: Iterable<string> | null | undefined,
): Set<string> {
  return new Set(keys ?? []);
}

export function canPermission(
  granted: ReadonlySet<string>,
  permission: string,
): boolean {
  return granted.has(permission);
}

export function canAnyPermission(
  granted: ReadonlySet<string>,
  permissions: readonly string[],
): boolean {
  if (permissions.length === 0) return true;
  return permissions.some((key) => granted.has(key));
}

export function canAllPermissions(
  granted: ReadonlySet<string>,
  permissions: readonly string[],
): boolean {
  if (permissions.length === 0) return true;
  return permissions.every((key) => granted.has(key));
}
