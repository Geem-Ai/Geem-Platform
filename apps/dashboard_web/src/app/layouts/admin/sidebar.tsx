import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { adminNav, type AdminNavItem } from './nav-config';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';

function NavLeaf({
  item,
  onNavigate,
}: {
  item: AdminNavItem;
  onNavigate?: () => void;
}) {
  const { t } = useTranslation();
  if (!item.to) return null;
  const Icon = item.icon;

  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      onClick={onNavigate}
      data-testid={`nav-${item.id}`}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
          isActive
            ? 'bg-primary/10 font-medium text-primary'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        )
      }
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{t(item.labelKey)}</span>
    </NavLink>
  );
}

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();

  return (
    <nav aria-label={t('shell.navigation')} data-testid="admin-nav">
      <ul className="space-y-4 px-2 py-3">
        {adminNav.map((item) => (
          <li key={item.id}>
            {item.children ? (
              <div>
                <p className="mb-1 px-2.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {t(item.labelKey)}
                </p>
                <ul className="space-y-0.5">
                  {item.children.map((child) => (
                    <li key={child.id}>
                      <NavLeaf item={child} onNavigate={onNavigate} />
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <NavLeaf item={item} onNavigate={onNavigate} />
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function Sidebar() {
  const { t } = useTranslation();

  return (
    <aside
      className="fixed inset-y-0 start-0 z-40 hidden w-[var(--sidebar-width)] border-e border-border bg-background lg:flex lg:flex-col"
      data-testid="admin-sidebar"
    >
      <div className="flex h-[var(--sidebar-header-height)] items-center gap-2.5 border-b border-border px-4">
        <img src="/brand/geem-avatar.webp" alt="" className="size-8 rounded-full" />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{t('app.product')}</p>
          <p className="truncate text-xs text-muted-foreground">{t('app.name')}</p>
        </div>
      </div>
      <ScrollArea className="flex-1">
        <SidebarNav />
      </ScrollArea>
    </aside>
  );
}
