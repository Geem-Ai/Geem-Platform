import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

export function OverviewPage() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-start gap-4 p-6 md:p-8 max-w-3xl">
      <Helmet>
        <title>
          {t('overview.title')} · {t('app.name')}
        </title>
      </Helmet>
      <div className="flex items-center gap-3">
        <img
          src={geemAvatarUrl()}
          alt={t('app.name')}
          className="size-12 rounded-full shadow-sm"
        />
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {t('overview.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('app.tagline')}</p>
        </div>
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed">
        {t('overview.description')}
      </p>
    </div>
  );
}
