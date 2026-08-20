import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';

export function ComingSoonPage({
  titleKey,
  phase,
}: {
  titleKey: string;
  phase: string;
}) {
  const { t } = useTranslation();
  const title = t(titleKey);

  return (
    <div
      className="mx-auto flex w-full max-w-3xl flex-col gap-3 p-6 md:p-8"
      data-testid="coming-soon-page"
    >
      <DocumentTitle title={title} />
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm leading-relaxed text-muted-foreground">{t('placeholder.body')}</p>
      <p className="text-xs text-muted-foreground/80">
        {t('placeholder.phaseHint', { phase })}
      </p>
    </div>
  );
}
