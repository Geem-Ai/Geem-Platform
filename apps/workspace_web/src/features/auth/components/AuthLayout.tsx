import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';
import { AuthBrandPanel } from './AuthBrandPanel';
import { AuthChrome } from './AuthChrome';

export function AuthLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  return (
    <div
      className="flex min-h-dvh w-full grow flex-col bg-background lg:flex-row"
      data-testid="auth-layout"
    >
      <AuthBrandPanel />

      <div className="flex min-h-dvh flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 px-5 py-4 sm:px-8 lg:justify-end">
          <Link
            to="/login"
            className="flex items-center gap-2.5 lg:hidden"
          >
            <img
              src={geemAvatarUrl()}
              alt=""
              className="size-9 rounded-full shadow-sm"
            />
            <span className="text-sm font-semibold tracking-tight">
              {t('app.name')}
            </span>
          </Link>
          <AuthChrome />
        </header>

        <main className="flex flex-1 flex-col items-center justify-center px-5 py-8 sm:px-8">
          <div className="w-full max-w-[400px] space-y-8">{children}</div>
        </main>

        <p className="px-5 pb-6 text-center text-xs text-muted-foreground lg:hidden">
          {t('auth.copyright', { year })}
        </p>
      </div>
    </div>
  );
}
