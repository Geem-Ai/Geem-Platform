import { useState } from 'react';
import {
  Building2,
  Check,
  Languages,
  LogOut,
  Monitor,
  Moon,
  Plus,
  Sun,
  UserRound,
} from 'lucide-react';
import { useTheme } from 'next-themes';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/features/auth/AuthProvider';
import { CreateWorkspaceDialog } from '@/features/workspaces/components/CreateWorkspaceDialog';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
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
import {
  Avatar,
  AvatarFallback,
} from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
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

interface AccountMenuProps {
  isCollapsed?: boolean;
}

type LogoutKind = 'session' | 'all';
type ThemeOption = 'light' | 'dark' | 'system';

const THEME_OPTIONS: ThemeOption[] = ['light', 'dark', 'system'];
const LOCALE_OPTIONS: AppLocale[] = ['en', 'ar'];

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

export function AccountMenu({ isCollapsed = false }: AccountMenuProps) {
  const { theme, setTheme } = useTheme();
  const { t, i18n } = useTranslation();
  const { user, logout, logoutAll } = useAuth();
  const { availableWorkspaces, currentWorkspace, selectWorkspace } = useWorkspace();
  const navigate = useNavigate();
  const locale = (i18n.language === 'ar' ? 'ar' : 'en') as AppLocale;
  const currentTheme: ThemeOption = isThemeOption(theme) ? theme : 'light';

  const [logoutKind, setLogoutKind] = useState<LogoutKind | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const setLocale = (next: AppLocale) => {
    void i18n.changeLanguage(next);
  };

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
                'flex items-center gap-2.5 lg:px-2 py-1.5 rounded-md hover:bg-muted transition-colors w-full',
              )}
              data-testid="account-menu-trigger"
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
          className="w-64"
          side="top"
          align="start"
          sideOffset={11}
        >
          <div className="flex items-center gap-2.5 px-2.5 py-1.5">
            <Avatar className="size-9">
              <AvatarFallback>{initials(user?.email)}</AvatarFallback>
            </Avatar>
            <div className="flex flex-col items-start min-w-0">
              <span className="text-sm font-semibold text-foreground truncate w-full">
                {user?.email ?? t('shell.accountPlaceholder')}
              </span>
              <span className="text-xs text-muted-foreground truncate w-full">
                {currentWorkspace?.name ?? t('shell.workspacePlaceholder')}
              </span>
            </div>
          </div>

          <DropdownMenuSeparator />

          <DropdownMenuLabel className="flex items-center gap-2">
            <Building2 className="size-3.5" />
            {t('shell.workspaces')}
          </DropdownMenuLabel>
          {availableWorkspaces.map((ws) => (
            <DropdownMenuItem
              key={ws.id}
              onClick={() => selectWorkspace(ws.id)}
              className="flex items-center justify-between gap-2"
            >
              <span className="truncate">
                {ws.name}
                <span className="ms-1 text-xs text-muted-foreground">
                  ({t(`roles.${ws.role}`)})
                </span>
              </span>
              {currentWorkspace?.id === ws.id && (
                <Check className="size-3.5 shrink-0" />
              )}
            </DropdownMenuItem>
          ))}
          <DropdownMenuItem
            onSelect={() => setCreateOpen(true)}
            data-testid="create-workspace-menu-item"
          >
            <Plus className="size-3.5" />
            {t('shell.createWorkspace')}
          </DropdownMenuItem>

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
                  if (value === 'en' || value === 'ar') setLocale(value);
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
          >
            <LogOut className="size-4" />
            {t('auth.logout')}
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onSelect={() => setLogoutKind('all')}
          >
            <LogOut className="size-4" />
            {t('auth.logoutAll')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <CreateWorkspaceDialog open={createOpen} onOpenChange={setCreateOpen} />

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
            <AlertDialogCancel disabled={loggingOut}>
              {t('common.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={loggingOut}
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
