import type { ReactNode } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';
import { marketingSiteUrl } from '@/lib/marketing-url';
import { AuthBrandPanel } from './AuthBrandPanel';
import { AuthChrome } from './AuthChrome';

export function AuthLayout({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const year = new Date().getFullYear();
  const homeUrl = marketingSiteUrl();
  const isRtl = i18n.language === 'ar';

  return (
    <div
      className="auth-page-canvas relative min-h-dvh w-full overflow-x-hidden bg-muted/30 lg:p-4 xl:p-6"
      data-testid="auth-layout"
    >
      <div className="auth-mobile-aurora" aria-hidden />

      <div className="auth-workspace-window relative mx-auto flex min-h-dvh w-full overflow-hidden bg-background lg:min-h-[calc(100dvh-2rem)] lg:max-w-[1500px] lg:rounded-[2rem] lg:border lg:border-border/80 xl:min-h-[calc(100dvh-3rem)]">
        <AuthBrandPanel />

        <div className="auth-form-pane relative flex min-h-dvh min-w-0 flex-1 flex-col lg:min-h-0">
          <header className="relative z-20 flex items-center justify-between gap-3 px-5 py-4 sm:px-8 sm:py-6">
            <a
              href={homeUrl}
              data-testid="auth-back-home"
              className="group flex min-w-0 items-center gap-2.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <span className="auth-mobile-brand-mark flex size-10 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-card/80 shadow-sm backdrop-blur-md transition-transform group-hover:scale-[1.03] lg:hidden">
                <img
                  src={geemAvatarUrl()}
                  alt=""
                  className="size-8 object-contain"
                />
              </span>
              <span className="inline-flex items-center gap-1.5 font-medium">
                <ArrowLeft
                  className={`size-4 shrink-0 ${isRtl ? 'rotate-180' : ''}`}
                  aria-hidden
                />
                <span className="truncate">{t('auth.backToHome')}</span>
              </span>
            </a>
            <AuthChrome />
          </header>

          <main className="relative z-10 flex flex-1 items-center justify-center px-4 py-6 sm:px-8 sm:py-8 lg:px-10 lg:py-10">
            <section className="auth-form-card relative w-full max-w-[460px] overflow-hidden rounded-[1.75rem] border border-border/80 bg-card/90 p-6 shadow-xl shadow-black/5 backdrop-blur-xl sm:p-8 dark:bg-card/85 dark:shadow-black/25">
              <div className="auth-form-card-glow" aria-hidden />
              <div className="relative z-10 space-y-7">{children}</div>
            </section>
          </main>

          <p className="relative z-10 px-5 pb-6 pt-2 text-center text-xs text-muted-foreground lg:hidden">
            {t('auth.copyright', { year })}
          </p>
        </div>
      </div>
    </div>
  );
}
