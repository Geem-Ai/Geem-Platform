import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';

export function ScreenLoader() {
  const { t } = useTranslation();

  return (
    <div
      className="flex flex-col items-center gap-3 justify-center fixed inset-0 z-50"
      data-testid="screen-loader"
    >
      <img
        src={geemAvatarUrl()}
        alt={t('app.name')}
        className="size-16 rounded-2xl"
      />
      <div className="text-muted-foreground font-medium text-sm">
        {t('shell.gettingReady')}
      </div>
    </div>
  );
}
