import { Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useLayout } from './context';
import { Header } from './header';
import { Sidebar } from './sidebar';

export function Wrapper() {
  const { isMobile } = useLayout();

  return (
    <div className="flex h-screen w-full min-w-0 [&_.container-fluid]:px-5">
      {!isMobile && <Sidebar />}

      <div
        className={cn(
          'flex flex-col flex-1 min-w-0 w-full pt-[var(--header-height-mobile)] lg:pt-0 transition-[padding] duration-300',
          // Logical padding clears the fixed sidebar in both LTR and RTL
          !isMobile &&
            'lg:ps-[calc(var(--sidebar-width-collapsed)+1.25rem)] lg:in-data-[sidebar-open=true]:ps-[calc(var(--sidebar-width)+1.25rem)]',
        )}
      >
        {isMobile && <Header />}
        <div className="flex grow min-w-0 w-full px-5 lg:pe-2.5 lg:ps-0 py-2.5">
          <div className="grow min-w-0 w-full bg-background overflow-y-auto border border-input rounded-xl shadow-xs">
            <main className="grow w-full min-w-0" role="main">
              <Outlet />
            </main>
          </div>
        </div>
      </div>
    </div>
  );
}
