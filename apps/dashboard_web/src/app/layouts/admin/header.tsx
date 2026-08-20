import { useEffect, useState } from 'react';
import { Menu } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTrigger } from '@/components/ui/sheet';
import { geemAvatarUrl } from '@/lib/helpers';
import { AccountMenu } from './account-menu';
import { SidebarNav } from './sidebar';

export function Header() {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  useEffect(() => {
    setIsSheetOpen(false);
  }, [pathname]);

  return (
    <header
      className="fixed inset-x-0 top-0 z-50 flex h-[var(--header-height-mobile)] items-center bg-background/95 backdrop-blur-sm lg:hidden"
      data-testid="admin-mobile-header"
    >
      <div className="flex w-full items-center justify-between gap-2 px-4">
        <div className="flex items-center gap-2">
          <Link to="/" className="flex items-center gap-2">
            <img src={geemAvatarUrl()} alt={t('app.name')} className="size-8 rounded-full" />
          </Link>
          <Sheet open={isSheetOpen} onOpenChange={setIsSheetOpen}>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                mode="icon"
                size="sm"
                aria-label={t('shell.menu')}
                data-testid="mobile-nav-trigger"
              >
                <Menu className="size-4" />
              </Button>
            </SheetTrigger>
            <SheetContent className="w-[255px] gap-0 p-0" side="start" close={false}>
              <SheetHeader className="space-y-0 p-0" />
              <SheetBody className="flex grow flex-col p-0">
                <div className="flex items-center gap-2 border-b border-border/60 px-3 py-3.5">
                  <img src={geemAvatarUrl()} alt="" className="size-8 rounded-full" />
                  <span className="text-sm font-medium">{t('app.product')}</span>
                </div>
                <SidebarNav onNavigate={() => setIsSheetOpen(false)} />
                <div className="mt-auto border-t border-border/60 p-2.5">
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
