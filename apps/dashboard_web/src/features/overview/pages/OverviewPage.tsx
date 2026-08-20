import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/features/auth/AuthProvider';
import { flattenAdminNav } from '@/app/layouts/admin/nav-config';

export function OverviewPage() {
  const { t } = useTranslation();
  const { user, me } = useAuth();
  const links = flattenAdminNav().filter((item) => item.id !== 'overview');

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6 md:p-8" data-testid="overview-page">
      <DocumentTitle title={t('overview.title')} />
      <header className="space-y-2">
        <p className="text-sm font-medium text-primary">{t('app.product')}</p>
        <h1 className="text-2xl font-semibold tracking-tight">{t('overview.welcome')}</h1>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{t('overview.context')}</p>
      </header>

      <Card data-testid="admin-identity-card">
        <CardHeader>
          <CardTitle>{t('overview.signedInAs')}</CardTitle>
          <CardDescription>{t('overview.roleLabel')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium">{user?.email}</span>
          <Badge appearance="light" data-testid="platform-role-badge">
            {me?.platform_role === 'admin'
              ? t('overview.roleAdmin')
              : (me?.platform_role ?? t('overview.roleAdmin'))}
          </Badge>
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-3 text-sm font-semibold">{t('overview.quickLinks')}</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {links.map((item) => (
            <Link
              key={item.id}
              to={item.to ?? '/'}
              className="rounded-xl border border-border bg-card p-4 shadow-xs transition-colors hover:bg-muted/60"
              data-testid={`overview-link-${item.id}`}
            >
              <p className="text-sm font-medium">{t(item.labelKey)}</p>
              {item.phase ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {t('overview.comingPhase', { phase: item.phase })}
                </p>
              ) : null}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
