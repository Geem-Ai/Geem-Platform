import { useMemo } from 'react';
import {
  ALL_PERMISSION_KEYS,
  canAllPermissions,
  canAnyPermission,
  canPermission,
  permissionSet,
} from '@/features/authz/permissions';
import { asRoleSummary, isOwnerRole } from '@/features/authz/role-summary';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';

export function usePermissions() {
  const { currentWorkspace, currentMembership } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? null;
  const role = asRoleSummary(
    currentMembership?.role ?? currentWorkspace?.role ?? null,
  );

  const granted = useMemo(() => {
    const listed =
      currentWorkspace?.permissions ?? currentMembership?.permissions ?? null;
    if (listed && listed.length > 0) {
      return permissionSet(listed);
    }
    if (isOwnerRole(role)) {
      return permissionSet(ALL_PERMISSION_KEYS);
    }
    return permissionSet(listed);
  }, [currentMembership?.permissions, currentWorkspace?.permissions, role]);

  return {
    workspaceId,
    role,
    permissions: granted,
    ready: Boolean(workspaceId),
    can: (permission: string) => canPermission(granted, permission),
    canAny: (permissions: readonly string[]) =>
      canAnyPermission(granted, permissions),
    canAll: (permissions: readonly string[]) =>
      canAllPermissions(granted, permissions),
  };
}
