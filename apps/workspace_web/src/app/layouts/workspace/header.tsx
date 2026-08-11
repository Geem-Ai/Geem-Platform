import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTrigger,
} from '@/components/ui/sheet';
import { geemAvatarUrl } from '@/lib/helpers';
import { AccountMenu } from './account-menu';
import { SidebarContent } from './sidebar-content';
import { WorkspaceSwitcher } from './workspace-switcher';

export function Header() {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  useEffect(() => {
    setIsSheetOpen(false);
  }, [pathname]);

  return (
    <header className="transition-[start,end] duration-300 fixed top-0 start-0 end-0 z-50 flex items-center shrink-0 bg-background/95 backdrop-blur-sm supports-backdrop-filter:bg-muted h-[var(--header-height-mobile)] pe-[var(--removed-body-scroll-bar-size,0px)]">
      <div className="container-fluid grow flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to="/" className="flex items-center gap-2">
            <img
              src={geemAvatarUrl()}
              alt={t('app.name')}
              className="size-8 rounded-full shadow-sm"
            />
          </Link>

          <Sheet open={isSheetOpen} onOpenChange={setIsSheetOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" mode="icon" size="sm">
                <Menu className="size-4" />
              </Button>
            </SheetTrigger>
            <SheetContent className="p-0 gap-0 w-[255px]" side="start" close={false}>
              <SheetHeader className="p-0 space-y-0" />
              <SheetBody className="flex grow flex-col p-0">
                <div className="px-3 py-3.5 flex items-center gap-2 border-b border-border/60">
                  <img
                    src={geemAvatarUrl()}
                    alt={t('app.name')}
                    className="size-8 rounded-full"
                  />
                  <span className="text-sm font-medium">{t('app.name')}</span>
                </div>
                <SidebarContent />
                <div className="mt-auto border-t border-border/60 p-2.5 space-y-1.5">
                  <WorkspaceSwitcher />
                  <AccountMenu />
                </div>
              </SheetBody>
            </SheetContent>
          </Sheet>
        </div>

        <AccountMenu isCollapsed />
      </div>
    </header>
  );
}
