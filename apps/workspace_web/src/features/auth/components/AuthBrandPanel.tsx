import { Globe2, ShieldCheck, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

const HIGHLIGHTS = [
  {
    icon: Globe2,
    titleKey: 'auth.highlightArabicTitle',
    bodyKey: 'auth.highlightArabicBody',
  },
  {
    icon: Sparkles,
    titleKey: 'auth.highlightExpertsTitle',
    bodyKey: 'auth.highlightExpertsBody',
  },
  {
    icon: ShieldCheck,
    titleKey: 'auth.highlightWorkspaceTitle',
    bodyKey: 'auth.highlightWorkspaceBody',
  },
] as const;

export function AuthBrandPanel() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  return (
    <aside
      className="auth-brand-panel relative hidden lg:flex lg:w-[46%] xl:w-[48%] shrink-0 flex-col overflow-hidden px-10 py-10 text-white"
      data-testid="auth-brand-panel"
    >
      <div className="auth-brand-light" />
      <div className="auth-brand-orb auth-brand-orb-a" />
      <div className="auth-brand-orb auth-brand-orb-b" />

      <div className="relative z-10 flex flex-1 flex-col">
        <div className="flex items-center gap-3">
          <div className="flex size-12 items-center justify-center overflow-hidden rounded-2xl bg-white/15 ring-1 ring-white/20">
            <img
              src={geemAvatarUrl()}
              alt=""
              className="size-10 object-contain"
            />
          </div>
          <div>
            <p className="text-lg font-semibold leading-none">{t('app.name')}</p>
            <p className="mt-1.5 text-sm text-white/70">{t('app.tagline')}</p>
          </div>
        </div>

        <div className="my-auto w-full space-y-6 py-10">
          <div className="max-w-lg space-y-3">
            <h2 className="text-3xl font-semibold tracking-tight text-white">
              {t('auth.brandHeadline')}
            </h2>
            <p className="text-sm leading-relaxed text-white/75">
              {t('auth.brandBody')}
            </p>
          </div>

          <ul className="max-w-md space-y-3">
            {HIGHLIGHTS.map(({ icon: Icon, titleKey, bodyKey }) => (
              <li
                key={titleKey}
                className="flex items-start gap-3 rounded-xl border border-white/15 bg-white/10 px-3.5 py-3 backdrop-blur-sm"
              >
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/15">
                  <Icon className="size-4 text-white" aria-hidden />
                </div>
                <div className="min-w-0 space-y-0.5">
                  <p className="text-sm font-medium leading-5 text-white">
                    {t(titleKey)}
                  </p>
                  <p className="text-xs leading-relaxed text-white/70">
                    {t(bodyKey)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-xs text-white/50">
          {t('auth.copyright', { year })}
        </p>
      </div>
    </aside>
  );
}
