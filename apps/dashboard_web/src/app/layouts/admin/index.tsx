import type { CSSProperties, ReactNode } from 'react';
import { Outlet } from 'react-router-dom';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ScreenLoader } from '@/components/shared/ScreenLoader';
import { useIsMobile } from '@/hooks/use-mobile';
import { AccountMenu } from './account-menu';
import { Header } from './header';
import { Sidebar } from './sidebar';

const layoutStyle = {
  '--sidebar-width': '255px',
  '--sidebar-header-height': '60px',
  '--header-height': '60px',
  '--header-height-mobile': '60px',
} as CSSProperties;

export function AdminLayout({ children }: { children?: ReactNode }) {
  const isMobile = useIsMobile();

  if (isMobile === undefined) {
    return <ScreenLoader />;
  }

  return (
    <TooltipProvider delayDuration={0}>
      <div
        className="flex h-screen w-full min-w-0 overflow-x-hidden bg-muted"
        style={layoutStyle}
        data-testid="admin-layout"
      >
        {!isMobile && <Sidebar />}
        <div
          className={
            isMobile
              ? 'flex min-w-0 w-full flex-1 flex-col pt-[var(--header-height-mobile)]'
              : 'flex min-w-0 w-full flex-1 flex-col lg:ps-[var(--sidebar-width)]'
          }
        >
          {isMobile && <Header />}
          {!isMobile && (
            <div className="flex h-[var(--header-height)] shrink-0 items-center justify-end border-b border-border/60 bg-background px-5">
              <AccountMenu isCollapsed />
            </div>
          )}
          <div className="flex min-w-0 w-full grow px-4 py-4 lg:px-6">
            <div className="min-w-0 w-full grow overflow-y-auto rounded-xl border border-input bg-background shadow-xs">
              <main className="min-w-0 w-full" role="main">
                {children ?? <Outlet />}
              </main>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
