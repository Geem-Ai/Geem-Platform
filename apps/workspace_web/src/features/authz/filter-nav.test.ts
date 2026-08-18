import { describe, expect, it } from 'vitest';
import { WorkspacePermission, canAllPermissions, canAnyPermission, canPermission, permissionSet } from './permissions';
import { filterNavByPermissions, firstAllowedNavPath } from './filter-nav';
import { workspaceNav } from '@/app/layouts/workspace/nav-config';

describe('permission helpers', () => {
  const granted = permissionSet([
    WorkspacePermission.CHAT_USE,
    WorkspacePermission.EXPERTS_VIEW,
    WorkspacePermission.WORKSPACE_VIEW,
  ]);

  it('can / canAny / canAll', () => {
    expect(canPermission(granted, WorkspacePermission.CHAT_USE)).toBe(true);
    expect(canPermission(granted, WorkspacePermission.BILLING_VIEW)).toBe(false);
    expect(
      canAnyPermission(granted, [
        WorkspacePermission.BILLING_VIEW,
        WorkspacePermission.EXPERTS_VIEW,
      ]),
    ).toBe(true);
    expect(canAnyPermission(granted, [WorkspacePermission.BILLING_VIEW])).toBe(false);
    expect(
      canAllPermissions(granted, [
        WorkspacePermission.CHAT_USE,
        WorkspacePermission.EXPERTS_VIEW,
      ]),
    ).toBe(true);
    expect(
      canAllPermissions(granted, [
        WorkspacePermission.CHAT_USE,
        WorkspacePermission.BILLING_VIEW,
      ]),
    ).toBe(false);
  });
});

describe('filterNavByPermissions', () => {
  it('keeps overview/chat/experts and hides empty parents', () => {
    const granted = permissionSet([
      WorkspacePermission.WORKSPACE_VIEW,
      WorkspacePermission.CHAT_USE,
      WorkspacePermission.EXPERTS_VIEW,
    ]);
    const items = filterNavByPermissions(workspaceNav, granted);
    expect(items.map((row) => row.id)).toEqual(['overview', 'chat', 'experts']);
    expect(items.find((row) => row.id === 'api')).toBeUndefined();
    expect(items.find((row) => row.id === 'billing')).toBeUndefined();
  });

  it('shows API parent only when a child is visible', () => {
    const granted = permissionSet([WorkspacePermission.API_USAGE_VIEW]);
    const items = filterNavByPermissions(workspaceNav, granted);
    const api = items.find((row) => row.id === 'api');
    expect(api?.children?.map((row) => row.id)).toEqual(['api-usage']);
  });

  it('firstAllowedNavPath prefers overview then chat', () => {
    const granted = permissionSet([
      WorkspacePermission.WORKSPACE_VIEW,
      WorkspacePermission.CHAT_USE,
    ]);
    expect(firstAllowedNavPath(workspaceNav, granted)).toBe('/overview');
  });
});
