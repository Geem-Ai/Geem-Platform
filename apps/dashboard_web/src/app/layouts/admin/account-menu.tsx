import { useState } from 'react';
import {
  Languages,
  LogOut,
  Monitor,
  Moon,
  Sun,
  UserRound,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/features/auth/AuthProvider';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { AppLocale } from '@/lib/i18n';
import { cn } from '@/lib/utils';

type LogoutKind = 'session' | 'all';
type ThemeOption = 'light' | 'dark' | 'system';

const THEME_OPTIONS: ThemeOption[] = ['light', 'dark', 'system'];
const LOCALE_OPTIONS: AppLocale[] = ['ar', 'en'];

function initials(email: string | undefined): string {
  if (!email) return '?';
  return email.slice(0, 2).toUpperCase();
}

function isThemeOption(value: string | undefined): value is ThemeOption {
  return value === 'light' || value === 'dark' || value === 'system';
}

function themeLabelKey(theme: ThemeOption): 'themeLight' | 'themeDark' | 'themeSystem' {
  if (theme === 'dark') return 'themeDark';
  if (theme === 'system') return 'themeSystem';
  return 'themeLight';
}

function ThemeGlyph({ theme }: { theme: ThemeOption }) {
  if (theme === 'dark') return <Moon className="size-4" />;
  if (theme === 'system') return <Monitor className="size-4" />;
  return <Sun className="size-4" />;
}

export function AccountMenu({ isCollapsed = false }: { isCollapsed?: boolean }) {
  const { theme, setTheme } = useTheme();
  const { t, i18n } = useTranslation();
  const { user, logout, logoutAll } = useAuth();
  const navigate = useNavigate();
  const locale = (i18n.language === 'en' ? 'en' : 'ar') as AppLocale;
  const currentTheme: ThemeOption = isThemeOption(theme) ? theme : 'light';
  const [logoutKind, setLogoutKind] = useState<LogoutKind | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  async function confirmLogout() {
    if (!logoutKind || loggingOut) return;
    setLoggingOut(true);
    try {
      if (logoutKind === 'all') {
        await logoutAll();
      } else {
        await logout();
      }
      setLogoutKind(null);
      navigate('/login', { replace: true });
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <>
      <DropdownMenu>
        {isCollapsed ? (
          <DropdownMenuTrigger className="cursor-pointer" data-testid="account-menu-trigger">
            <Avatar className="size-9">
              <AvatarFallback>{initials(user?.email)}</AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
        ) : (
          <DropdownMenuTrigger className="cursor-pointer" asChild>
            <div
              className={cn(
                'flex w-full items-center gap-2.5 rounded-md py-1.5 hover:bg-muted lg:px-2',
              )}
              data-testid="account-menu-trigger"
            >
              <Avatar className="size-9">
                <AvatarFallback>
                  {user?.email ? initials(user.email) : <UserRound className="size-4" />}
                </AvatarFallback>
              </Avatar>
              <div className="hidden min-w-0 flex-1 flex-col items-start lg:flex">
                <span className="w-full truncate text-sm font-semibold">{user?.email}</span>
                <span className="w-full truncate text-xs text-muted-foreground">
                  {t('overview.roleAdmin')}
                </span>
              </div>
            </div>
          </DropdownMenuTrigger>
        )}

        <DropdownMenuContent className="w-64" side="top" align="start" sideOffset={11}>
          <div className="flex items-center gap-2.5 px-2.5 py-1.5">
            <Avatar className="size-9">
              <AvatarFallback>{initials(user?.email)}</AvatarFallback>
            </Avatar>
            <div className="flex min-w-0 flex-col items-start">
              <span className="w-full truncate text-sm font-semibold">{user?.email}</span>
              <span className="w-full truncate text-xs text-muted-foreground">
                {t('app.product')}
              </span>
            </div>
          </div>

          <DropdownMenuSeparator />

          <DropdownMenuSub>
            <DropdownMenuSubTrigger data-testid="theme-menu">
              <ThemeGlyph theme={currentTheme} />
              <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                <span>{t('shell.theme')}</span>
                <span className="text-xs text-muted-foreground">
                  {t(`shell.${themeLabelKey(currentTheme)}`)}
                </span>
              </span>
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="min-w-40">
              <DropdownMenuRadioGroup
                value={currentTheme}
                onValueChange={(value) => {
                  if (isThemeOption(value)) setTheme(value);
                }}
              >
                {THEME_OPTIONS.map((option) => (
                  <DropdownMenuRadioItem
                    key={option}
                    value={option}
                    data-testid={`theme-option-${option}`}
                  >
                    {t(`shell.${themeLabelKey(option)}`)}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuSubContent>
          </DropdownMenuSub>

          <DropdownMenuSub>
            <DropdownMenuSubTrigger data-testid="language-menu">
              <Languages className="size-4" />
              <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                <span>{t('shell.language')}</span>
                <span className="text-xs text-muted-foreground">
                  {t(locale === 'ar' ? 'shell.languageAr' : 'shell.languageEn')}
                </span>
              </span>
            </DropdownMenuSubTrigger>
            <DropdownMenuSubContent className="min-w-40">
              <DropdownMenuRadioGroup
                value={locale}
                onValueChange={(value) => {
                  if (value === 'en' || value === 'ar') void i18n.changeLanguage(value);
                }}
              >
                {LOCALE_OPTIONS.map((option) => (
                  <DropdownMenuRadioItem
                    key={option}
                    value={option}
                    data-testid={`language-option-${option}`}
                  >
                    {t(option === 'ar' ? 'shell.languageAr' : 'shell.languageEn')}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuSubContent>
          </DropdownMenuSub>

          <DropdownMenuSeparator />

          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setLogoutKind('session')}
            data-testid="logout-menu-item"
          >
            <LogOut className="size-4" />
            {t('auth.logout')}
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => setLogoutKind('all')}>
            <LogOut className="size-4" />
            {t('auth.logoutAll')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog
        open={logoutKind !== null}
        onOpenChange={(open) => {
          if (!open && !loggingOut) setLogoutKind(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {logoutKind === 'all'
                ? t('auth.logoutAllConfirmTitle')
                : t('auth.logoutConfirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {logoutKind === 'all'
                ? t('auth.logoutAllConfirmHint')
                : t('auth.logoutConfirmHint')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={loggingOut}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={loggingOut}
              data-testid="logout-confirm"
              onClick={(e) => {
                e.preventDefault();
                void confirmLogout();
              }}
            >
              {loggingOut
                ? t('auth.loggingOut')
                : logoutKind === 'all'
                  ? t('auth.logoutAll')
                  : t('auth.logout')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
