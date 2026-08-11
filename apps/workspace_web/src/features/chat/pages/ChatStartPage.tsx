import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

/** Minimal AI Concept–inspired placeholder. Full Chat UI is Phase 4. */
export function ChatStartPage() {
  const { t } = useTranslation();

  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center gap-4 p-6 text-center">
      <Helmet>
        <title>
          {t('chat.title')} · {t('app.name')}
        </title>
      </Helmet>
      <img
        src={geemAvatarUrl()}
        alt={t('app.name')}
        className="size-16 rounded-full shadow-md"
      />
      <h1 className="text-xl font-semibold tracking-tight">{t('chat.title')}</h1>
      <p className="max-w-md text-sm text-muted-foreground leading-relaxed">
        {t('chat.placeholder')}
      </p>
    </div>
  );
}
