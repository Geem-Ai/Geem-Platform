import { useLayout } from './context';
import { AccountMenu } from './account-menu';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export function SidebarFooter() {
  const { t, i18n } = useTranslation();
  const { isSidebarOpen, sidebarMode, setSidebarMode } = useLayout();
  const collapsed = !isSidebarOpen;
  const tooltipSide = i18n.language === 'ar' ? 'left' : 'right';
  const showWorkspaceSettings = sidebarMode === 'chat';

  const settingsButton = (
    <Button
      type="button"
      variant="ghost"
      className={cn(
        'w-full justify-start gap-2.5 px-2.5 text-sm text-muted-foreground hover:text-foreground',
        collapsed && 'justify-center px-0 size-10',
      )}
      onClick={() => setSidebarMode('workspace')}
      data-testid="workspace-settings-button"
      aria-label={t('shell.workspaceSettings')}
    >
      <Settings className="size-4 shrink-0" />
      {!collapsed && <span className="truncate">{t('shell.workspaceSettings')}</span>}
    </Button>
  );

  return (
    <div className="shrink-0 lg:px-2.5 py-2.5 space-y-1.5 border-t border-border/60">
      {showWorkspaceSettings &&
        (collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>{settingsButton}</TooltipTrigger>
            <TooltipContent side={tooltipSide}>
              {t('shell.workspaceSettings')}
            </TooltipContent>
          </Tooltip>
        ) : (
          settingsButton
        ))}
      <AccountMenu isCollapsed={collapsed} />
    </div>
  );
}
