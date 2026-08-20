import { ShieldCheck, Server, ScrollText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

const HIGHLIGHTS = [
  {
    icon: Server,
    titleKey: 'auth.highlightHostTitle',
    bodyKey: 'auth.highlightHostBody',
  },
  {
    icon: ShieldCheck,
    titleKey: 'auth.highlightRoleTitle',
    bodyKey: 'auth.highlightRoleBody',
  },
  {
    icon: ScrollText,
    titleKey: 'auth.highlightAuditTitle',
    bodyKey: 'auth.highlightAuditBody',
  },
] as const;

export function AuthBrandPanel() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  return (
    <aside
      className="auth-brand-panel relative hidden shrink-0 flex-col overflow-hidden px-10 py-9 text-white lg:flex lg:w-[48%] xl:w-1/2 xl:px-14 xl:py-11"
      data-testid="auth-brand-panel"
    >
      <div className="auth-brand-grid" aria-hidden />
      <div className="auth-brand-light" aria-hidden />
      <div className="auth-brand-orb auth-brand-orb-a" aria-hidden />
      <div className="auth-brand-orb auth-brand-orb-b" aria-hidden />

      <div className="relative z-10 flex flex-1 flex-col">
        <div className="flex items-center gap-3">
          <div className="auth-brand-mark flex size-12 items-center justify-center overflow-hidden rounded-2xl bg-white/15 ring-1 ring-white/25 backdrop-blur-md">
            <img src={geemAvatarUrl()} alt="" className="size-9 object-contain" />
          </div>
          <div>
            <p className="text-lg font-semibold leading-none">{t('app.product')}</p>
            <p className="mt-1.5 text-sm text-white/70">{t('app.tagline')}</p>
          </div>
        </div>

        <div className="my-auto w-full max-w-2xl py-10">
          <div className="max-w-xl space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-medium text-white/90">
              <ShieldCheck className="size-3.5" aria-hidden />
              <span>{t('auth.brandEyebrow')}</span>
            </div>
            <h2 className="max-w-lg text-4xl font-semibold leading-[1.15] tracking-tight text-white">
              {t('auth.brandHeadline')}
            </h2>
            <p className="max-w-lg text-sm leading-7 text-white/75">{t('auth.brandBody')}</p>
          </div>

          <ul className="mt-8 space-y-3">
            {HIGHLIGHTS.map((item) => (
              <li
                key={item.titleKey}
                className="flex gap-3 rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-md"
              >
                <item.icon className="mt-0.5 size-4 shrink-0 text-white/90" aria-hidden />
                <div>
                  <p className="text-sm font-semibold">{t(item.titleKey)}</p>
                  <p className="mt-1 text-xs leading-5 text-white/70">{t(item.bodyKey)}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-xs text-white/55">{t('auth.copyright', { year })}</p>
      </div>
    </aside>
  );
}
