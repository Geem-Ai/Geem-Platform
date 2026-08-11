import { SidebarContent } from './sidebar-content';
import { SidebarFooter } from './sidebar-footer';
import { SidebarHeader } from './sidebar-header';
import { useLayout } from './context';

export function Sidebar() {
  const { isSidebarOpen } = useLayout();

  return (
    <aside className="fixed overflow-hidden bg-background rounded-xl top-2.5 bottom-2.5 start-2.5 z-20 transition-all duration-300 flex flex-col shrink-0 w-(--sidebar-width) max-w-(--sidebar-width) in-data-[sidebar-open=false]:w-(--sidebar-width-collapsed) in-data-[sidebar-open=false]:max-w-(--sidebar-width-collapsed) border border-input">
      <div
        className="h-full min-h-0 min-w-0 max-w-full transition-all duration-300 flex flex-col overflow-hidden"
        style={{
          width: isSidebarOpen
            ? 'var(--sidebar-width)'
            : 'var(--sidebar-width-collapsed)',
        }}
      >
        <SidebarHeader />
        <SidebarContent />
        <SidebarFooter />
      </div>
    </aside>
  );
}
