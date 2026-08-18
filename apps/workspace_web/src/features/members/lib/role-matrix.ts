/** UX capability matrix aligned with backend `WorkspacePolicy`. Not authoritative. */

export type MatrixRole = 'owner' | 'admin' | 'member';

export type RoleMatrixRow = {
  id: string;
  groupKey: string;
  labelKey: string;
  owner: boolean;
  admin: boolean;
  member: boolean;
};

export const ROLE_MATRIX_GROUPS = [
  'workspace',
  'members',
  'knowledge',
  'apps',
  'api',
] as const;

export const ROLE_MATRIX_ROWS: readonly RoleMatrixRow[] = [
  {
    id: 'read_workspace',
    groupKey: 'workspace',
    labelKey: 'members.matrix.viewWorkspace',
    owner: true,
    admin: true,
    member: true,
  },
  {
    id: 'update_workspace',
    groupKey: 'workspace',
    labelKey: 'members.matrix.updateWorkspace',
    owner: true,
    admin: true,
    member: false,
  },
  {
    id: 'delete_workspace',
    groupKey: 'workspace',
    labelKey: 'members.matrix.deleteWorkspace',
    owner: true,
    admin: false,
    member: false,
  },
  {
    id: 'view_members',
    groupKey: 'members',
    labelKey: 'members.matrix.viewMembers',
    owner: true,
    admin: true,
    member: true,
  },
  {
    id: 'manage_members',
    groupKey: 'members',
    labelKey: 'members.matrix.manageMembers',
    owner: true,
    admin: true,
    member: false,
  },
  {
    id: 'change_member_roles',
    groupKey: 'members',
    labelKey: 'members.matrix.changeRoles',
    owner: true,
    admin: true,
    member: false,
  },
  {
    id: 'promote_to_owner',
    groupKey: 'members',
    labelKey: 'members.matrix.promoteOwner',
    owner: true,
    admin: false,
    member: false,
  },
  {
    id: 'knowledge',
    groupKey: 'knowledge',
    labelKey: 'members.matrix.manageKnowledge',
    owner: true,
    admin: true,
    member: true,
  },
  {
    id: 'manage_apps',
    groupKey: 'apps',
    labelKey: 'members.matrix.manageApps',
    owner: true,
    admin: true,
    member: false,
  },
  {
    id: 'manage_api_keys',
    groupKey: 'api',
    labelKey: 'members.matrix.manageApiKeys',
    owner: true,
    admin: true,
    member: false,
  },
];

export const INVITE_ROLES = ['admin', 'member'] as const;
