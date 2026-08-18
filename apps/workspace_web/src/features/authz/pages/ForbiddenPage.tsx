import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ShieldOff } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';

export function ForbiddenPage() {
  const { t } = useTranslation();
  return (
    <div
      className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center"
      data-testid="forbidden-page"
    >
      <DocumentTitle title={t('errors.forbiddenTitle')} />
      <ShieldOff className="size-10 text-muted-foreground" aria-hidden />
      <div className="space-y-2 max-w-md">
        <h1 className="text-xl font-semibold tracking-tight">
          {t('errors.forbiddenTitle')}
        </h1>
        <p className="text-sm text-muted-foreground leading-relaxed">
          {t('errors.forbiddenPage')}
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to="/">{t('errors.goHome')}</Link>
      </Button>
    </div>
  );
}
