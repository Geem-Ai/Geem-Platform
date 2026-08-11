import { Outlet } from 'react-router-dom';
import { useLayout } from './context';
import { Header } from './header';
import { Sidebar } from './sidebar';

export function Wrapper() {
  const { isMobile } = useLayout();

  return (
    <div className="flex h-screen w-full [&_.container-fluid]:px-5">
      {!isMobile && <Sidebar />}

      <div className="flex flex-col flex-1 min-w-0 w-full pt-[var(--header-height-mobile)] lg:pt-0">
        {isMobile && <Header />}
        <div className="flex grow lg:mx-2.5 mx-5 py-2.5">
          <div className="grow bg-background overflow-y-auto transition-all duration-300 lg:ms-[calc(var(--sidebar-width-collapsed)+0.6rem)] lg:in-data-[sidebar-open=true]:ms-[calc(var(--sidebar-width)+0.6rem)] border border-input rounded-xl shadow-xs">
            <main className="grow" role="main">
              <Outlet />
            </main>
          </div>
        </div>
      </div>
    </div>
  );
}
