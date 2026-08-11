import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

export function ScreenLoader() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center gap-2 justify-center fixed inset-0 z-50 transition-opacity duration-700 ease-in-out">
      <img
        className="h-10 w-10 rounded-full max-w-none"
        src={geemAvatarUrl()}
        alt={t('app.name')}
      />
      <div className="text-muted-foreground font-medium text-sm">
        {t('shell.loading')}
      </div>
    </div>
  );
}
