import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useLayout } from './context';
import { workspaceNav, type NavItem } from './nav-config';

function NavLinkItem({
  item,
  collapsed,
  nested = false,
}: {
  item: NavItem;
  collapsed: boolean;
  nested?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const label = t(item.labelKey);
  const Icon = item.icon;
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';

  const link = (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
          nested && 'ms-4',
          isActive
            ? 'bg-accent text-accent-foreground font-medium'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
          collapsed && 'justify-center px-0',
        )
      }
    >
      <Icon className="size-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );

  if (!collapsed) {
    return link;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}

export function SidebarContent() {
  const { t, i18n } = useTranslation();
  const { isSidebarOpen } = useLayout();
  const collapsed = !isSidebarOpen;
  const dir = i18n.language === 'ar' ? 'rtl' : 'ltr';

  return (
    <ScrollArea dir={dir} className="min-h-0 flex-1 w-full">
      <nav className="p-2.5 space-y-1" aria-label={t('shell.workspacePlaceholder')}>
        {workspaceNav.map((item) => (
          <div key={item.id} className="space-y-1">
            <NavLinkItem item={item} collapsed={collapsed} />
            {!collapsed &&
              item.children?.map((child) => (
                <NavLinkItem
                  key={child.id}
                  item={child}
                  collapsed={collapsed}
                  nested
                />
              ))}
            {!collapsed && item.children && (
              <Separator className="my-2 opacity-80" />
            )}
          </div>
        ))}
      </nav>
    </ScrollArea>
  );
}
