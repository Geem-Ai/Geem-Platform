import { canAnyPermission } from '@/features/authz/permissions';
import type { NavItem } from '@/app/layouts/workspace/nav-config';

export function filterNavByPermissions(
  items: readonly NavItem[],
  granted: ReadonlySet<string>,
): NavItem[] {
  const visible: NavItem[] = [];
  for (const item of items) {
    if (item.children?.length) {
      const children = filterNavByPermissions(item.children, granted);
      if (children.length === 0) continue;
      visible.push({ ...item, children });
      continue;
    }
    if (!canAnyPermission(granted, item.permissions ?? [])) continue;
    visible.push(item);
  }
  return visible;
}

export function firstAllowedNavPath(
  items: readonly NavItem[],
  granted: ReadonlySet<string>,
): string | null {
  for (const item of filterNavByPermissions(items, granted)) {
    if (item.to) return item.to;
    if (item.children?.length) {
      const child = item.children.find((row) => row.to);
      if (child?.to) return child.to;
    }
  }
  return null;
}

export function requiredPermissionsForPath(
  pathname: string,
  items: readonly NavItem[],
): string[] | null {
  for (const item of items) {
    if (item.to && pathMatches(pathname, item.to)) {
      return item.permissions ?? [];
    }
    if (item.children?.length) {
      const nested = requiredPermissionsForPath(pathname, item.children);
      if (nested) return nested;
    }
  }
  return null;
}

function pathMatches(pathname: string, to: string): boolean {
  if (pathname === to) return true;
  if (to === '/chat') return pathname === '/chat' || pathname.startsWith('/chat/');
  if (to === '/experts') {
    return pathname === '/experts' || pathname.startsWith('/experts/');
  }
  if (to === '/apps') return pathname === '/apps' || pathname.startsWith('/apps/');
  if (to === '/storage') {
    return pathname === '/storage' || pathname.startsWith('/storage/');
  }
  if (to === '/members') {
    return pathname === '/members' || pathname.startsWith('/members/');
  }
  if (to === '/settings') {
    return pathname === '/settings' || pathname.startsWith('/settings/');
  }
  if (to === '/overview') return pathname === '/overview';
  return pathname === to || pathname.startsWith(`${to}/`);
}
