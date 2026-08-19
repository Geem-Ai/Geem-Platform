import { FileText, Globe2, ShieldCheck, Sparkles } from 'lucide-react';
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
      className="auth-brand-panel relative hidden shrink-0 flex-col overflow-hidden px-10 py-9 text-white lg:flex lg:w-[48%] xl:w-1/2 xl:px-14 xl:py-11"
      data-testid="auth-brand-panel"
    >
      <div className="auth-brand-grid" aria-hidden />
      <div className="auth-brand-light" aria-hidden />
      <div className="auth-brand-orb auth-brand-orb-a" aria-hidden />
      <div className="auth-brand-orb auth-brand-orb-b" aria-hidden />
      <span className="auth-brand-star auth-brand-star-a" aria-hidden />
      <span className="auth-brand-star auth-brand-star-b" aria-hidden />
      <span className="auth-brand-star auth-brand-star-c" aria-hidden />

      <div className="relative z-10 flex flex-1 flex-col">
        <div className="flex items-center gap-3">
          <div className="auth-brand-mark flex size-12 items-center justify-center overflow-hidden rounded-2xl bg-white/15 ring-1 ring-white/25 backdrop-blur-md">
            <img
              src={geemAvatarUrl()}
              alt=""
              className="size-9 object-contain"
            />
          </div>
          <div>
            <p className="text-lg font-semibold leading-none">{t('app.name')}</p>
            <p className="mt-1.5 text-sm text-white/70">{t('app.tagline')}</p>
          </div>
        </div>

        <div className="auth-brand-story my-auto w-full max-w-2xl py-10 xl:py-12">
          <div className="max-w-xl space-y-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-medium text-white/90 backdrop-blur-md">
              <Sparkles className="size-3.5" aria-hidden />
              <span>{t('auth.brandEyebrow')}</span>
            </div>
            <h2 className="max-w-lg text-4xl font-semibold leading-[1.15] tracking-tight text-white xl:text-[2.75rem]">
              {t('auth.brandHeadline')}
            </h2>
            <p className="max-w-lg text-sm leading-7 text-white/75 xl:text-base">
              {t('auth.brandBody')}
            </p>
          </div>

          <div className="auth-brand-preview mt-8 rounded-[1.75rem] border border-white/20 bg-white/10 p-5 shadow-2xl shadow-black/15 backdrop-blur-xl xl:p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="flex size-8 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/15">
                  <img src={geemAvatarUrl()} alt="" className="size-6 object-contain" />
                </div>
                <span className="text-sm font-semibold text-white">{t('app.name')}</span>
              </div>
              <span className="rounded-full border border-white/15 bg-[#0e2f44]/70 px-2.5 py-1 text-[11px] font-medium text-white">
                {t('auth.previewSources')}
              </span>
            </div>

            <div className="mt-5 flex justify-end">
              <p className="max-w-[84%] rounded-2xl rounded-ee-md bg-[#0e2f44]/45 px-4 py-3 text-sm leading-6 text-white ring-1 ring-white/10">
                {t('auth.previewQuestion')}
              </p>
            </div>

            <div className="mt-3 flex items-start gap-3">
              <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-xl bg-white text-brand shadow-lg shadow-black/10">
                <Sparkles className="size-4" aria-hidden />
              </div>
              <div className="min-w-0 flex-1 rounded-2xl rounded-es-md bg-[#0e2f44]/55 px-4 py-3 ring-1 ring-white/10">
                <p className="text-sm leading-6 text-white">
                  {t('auth.previewAnswer')}
                </p>
                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-white/90">
                  <FileText className="size-3" aria-hidden />
                  <span>{t('auth.previewSources')}</span>
                </div>
              </div>
            </div>
          </div>

          <ul className="mt-5 grid grid-cols-3 gap-2.5">
            {HIGHLIGHTS.map(({ icon: Icon, titleKey, bodyKey }) => (
              <li
                key={titleKey}
                className="group rounded-2xl border border-white/15 bg-white/[0.08] px-3 py-3 text-center backdrop-blur-sm transition-colors hover:bg-white/[0.12]"
              >
                <div className="auth-highlight-icon mx-auto flex size-8 items-center justify-center rounded-xl bg-white/10 transition-transform group-hover:-translate-y-0.5">
                  <Icon className="size-4 text-white" aria-hidden />
                </div>
                <p className="mt-2 text-xs font-medium leading-5 text-white/85">
                  {t(titleKey)}
                </p>
                <p className="mt-1 text-[11px] leading-4 text-white/75">
                  {t(bodyKey)}
                </p>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative z-10 flex items-center justify-between gap-4 text-xs text-white/50">
          <p>{t('auth.copyright', { year })}</p>
          <p className="flex items-center gap-1.5">
            <ShieldCheck className="size-3.5" aria-hidden />
            <span>{t('auth.secureAccess')}</span>
          </p>
        </div>
      </div>
    </aside>
  );
}
