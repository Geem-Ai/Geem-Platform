import { useLayout } from './context';
import { AccountMenu } from './account-menu';
import { WorkspaceSwitcher } from './workspace-switcher';

export function SidebarFooter() {
  const { isSidebarOpen } = useLayout();

  return (
    <div className="shrink-0 lg:px-2.5 py-2.5 space-y-1.5 border-t border-border/60">
      <WorkspaceSwitcher collapsed={!isSidebarOpen} />
      <AccountMenu isCollapsed={!isSidebarOpen} />
    </div>
  );
}
