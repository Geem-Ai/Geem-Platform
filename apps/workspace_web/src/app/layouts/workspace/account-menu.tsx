import { Languages, LogOut, Moon, Sun, UserRound } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/features/auth/AuthProvider';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import {
  Avatar,
  AvatarFallback,
} from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { AppLocale } from '@/lib/i18n';
import { cn } from '@/lib/utils';

interface AccountMenuProps {
  isCollapsed?: boolean;
}

function initials(email: string | undefined): string {
  if (!email) return '?';
  return email.slice(0, 2).toUpperCase();
}

export function AccountMenu({ isCollapsed = false }: AccountMenuProps) {
  const { theme, setTheme } = useTheme();
  const { t, i18n } = useTranslation();
  const { user, logout, logoutAll } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const locale = (i18n.language === 'ar' ? 'ar' : 'en') as AppLocale;

  const setLocale = (next: AppLocale) => {
    void i18n.changeLanguage(next);
  };

  const onLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const onLogoutAll = async () => {
    await logoutAll();
    navigate('/login', { replace: true });
  };

  return (
    <DropdownMenu>
      {isCollapsed ? (
        <DropdownMenuTrigger className="cursor-pointer">
          <Avatar className="size-9">
            <AvatarFallback>{initials(user?.email)}</AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>
      ) : (
        <DropdownMenuTrigger className="cursor-pointer" asChild>
          <div
            className={cn(
              'flex items-center gap-2.5 lg:px-2 py-1.5 rounded-md hover:bg-muted transition-colors w-full',
            )}
          >
            <Avatar className="size-9">
              <AvatarFallback>
                {user?.email ? initials(user.email) : <UserRound className="size-4" />}
              </AvatarFallback>
            </Avatar>
            <div className="hidden lg:flex flex-col items-start flex-1 min-w-0">
              <span className="text-sm font-semibold text-foreground truncate w-full">
                {user?.email ?? t('shell.accountPlaceholder')}
              </span>
              <span className="text-xs text-muted-foreground truncate w-full">
                {currentWorkspace?.name ?? t('shell.workspacePlaceholder')}
              </span>
            </div>
          </div>
        </DropdownMenuTrigger>
      )}

      <DropdownMenuContent
        className="w-56"
        side="top"
        align="start"
        sideOffset={11}
      >
        <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
        <DropdownMenuItem disabled className="text-xs text-muted-foreground">
          {currentWorkspace?.name}
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
          {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
          <span>{theme === 'dark' ? t('shell.themeLight') : t('shell.themeDark')}</span>
        </DropdownMenuItem>

        <DropdownMenuItem onClick={() => setTheme('system')}>
          <Sun className="size-4 opacity-60" />
          <span>{t('shell.themeSystem')}</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-2">
          <Languages className="size-3.5" />
          {t('shell.language')}
        </DropdownMenuLabel>
        <DropdownMenuItem
          onClick={() => setLocale('en')}
          className={locale === 'en' ? 'bg-accent' : undefined}
        >
          {t('shell.languageEn')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setLocale('ar')}
          className={locale === 'ar' ? 'bg-accent' : undefined}
        >
          {t('shell.languageAr')}
        </DropdownMenuItem>

        <DropdownMenuSeparator />

        <DropdownMenuItem onClick={() => void onLogout()}>
          <LogOut className="size-4" />
          {t('auth.logout')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => void onLogoutAll()}>
          <LogOut className="size-4" />
          {t('auth.logoutAll')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
