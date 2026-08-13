import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';

type PlaceholderPageProps = {
  titleKey: string;
  descriptionKey?: string;
};

export function PlaceholderPage({
  titleKey,
  descriptionKey = 'shell.pagePlaceholder',
}: PlaceholderPageProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-3 p-6 md:p-8 w-full max-w-3xl ms-auto me-auto">
      <DocumentTitle title={t(titleKey)} />
      <h1 className="text-xl font-semibold tracking-tight">{t(titleKey)}</h1>
      <p className="text-sm text-muted-foreground leading-relaxed">
        {t(descriptionKey)}
      </p>
      <p className="text-xs text-muted-foreground/80">{t('shell.comingSoon')}</p>
    </div>
  );
}
