import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

export function AuthLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();

  return (
    // body/#root are Metronic flex row; grow + w-full so auth fills the viewport
    <div className="grow w-full min-h-dvh flex flex-col bg-muted">
      <div className="flex-1 flex flex-col items-center justify-center p-6">
        <div className="w-full max-w-md space-y-6">
          <div className="flex flex-col items-center gap-3 text-center">
            <img
              src={geemAvatarUrl()}
              alt={t('app.name')}
              className="size-14 rounded-full shadow-sm"
            />
            <div>
              <h1 className="text-xl font-semibold tracking-tight">{t('app.name')}</h1>
              <p className="text-sm text-muted-foreground">{t('app.tagline')}</p>
            </div>
          </div>
          {children}
        </div>
      </div>
      <p className="pb-6 text-center text-xs text-muted-foreground">
        <Link to="/login" className="hover:underline">
          {t('app.name')}
        </Link>
      </p>
    </div>
  );
}
