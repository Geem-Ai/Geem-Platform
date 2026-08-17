import { useTranslation } from 'react-i18next';
import { GeemAnimatedMascot } from '@/components/brand/GeemAnimatedMascot';

export function ScreenLoader() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center gap-3 justify-center fixed inset-0 z-50 transition-opacity duration-700 ease-in-out">
      <GeemAnimatedMascot
        alt={t('app.name')}
        className="size-28"
        data-testid="geem-screen-loader-mascot"
      />
      <div className="text-muted-foreground font-medium text-sm">
        {t('shell.gettingReady')}
      </div>
    </div>
  );
}
