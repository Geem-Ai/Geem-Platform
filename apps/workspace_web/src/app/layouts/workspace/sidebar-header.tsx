import { PanelLeft } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { geemAvatarUrl } from '@/lib/helpers';
import { useLayout } from './context';

export function SidebarHeader() {
  const { sidebarToggle, isSidebarOpen } = useLayout();
  const { t } = useTranslation();

  const toggleIcon = (
    <PanelLeft
      className={
        isSidebarOpen ? 'rtl:rotate-180' : 'rotate-180 rtl:rotate-0'
      }
    />
  );

  if (!isSidebarOpen) {
    return (
      <div className="flex items-center justify-center shrink-0 px-2.5 py-3.5">
        <Button
          mode="icon"
          variant="ghost"
          onClick={() => sidebarToggle()}
          className="hidden lg:inline-flex shrink-0"
          aria-label={t('shell.expandSidebar')}
        >
          {toggleIcon}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between shrink-0 px-3 py-3.5">
      <Link to="/chat" className="flex items-center gap-2 min-w-0">
        <img
          src={geemAvatarUrl()}
          alt={t('app.name')}
          className="size-8 rounded-full shadow-sm"
        />
        <span className="text-sm font-medium truncate">{t('app.name')}</span>
      </Link>

      <Button
        mode="icon"
        variant="ghost"
        onClick={() => sidebarToggle()}
        className="hidden lg:inline-flex shrink-0"
        aria-label={t('shell.collapseSidebar')}
      >
        {toggleIcon}
      </Button>
    </div>
  );
}
