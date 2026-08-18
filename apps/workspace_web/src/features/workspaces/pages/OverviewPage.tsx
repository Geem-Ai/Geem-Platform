import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { useAuth } from '@/features/auth/AuthProvider';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { usePermissions } from '@/features/authz/usePermissions';
import { roleDisplayName } from '@/features/authz/role-summary';
import { canCreateExpert } from '@/features/experts/lib/capabilities';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { ExpertCard } from '@/features/experts/components/ExpertCard';
import { OverviewRecommendedApps } from '@/features/apps/components/OverviewRecommendedApps';
import { OverviewUsageSummary } from '@/features/usage/components/OverviewUsageSummary';
import { geemAvatarUrl } from '@/lib/helpers';

export function OverviewPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const { can, role } = usePermissions();
  const canCreate = canCreateExpert(can);
  const expertsQuery = useExperts();
  const experts = (expertsQuery.data ?? []).filter((e) => e.status === 'ready').slice(0, 4);

  return (
    <div className="flex flex-col gap-6 p-6 md:p-8 w-full max-w-3xl ms-auto me-auto">
      <DocumentTitle title={t('overview.title')} />
      <div className="flex items-center gap-3">
        <img
          src={geemAvatarUrl()}
          alt={t('app.name')}
          className="size-12 rounded-full shadow-sm"
        />
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            {t('overview.welcome', { name: currentWorkspace?.name ?? t('app.name') })}
          </h1>
          <p className="text-sm text-muted-foreground">
            {user?.email} · {roleDisplayName(role) || t('app.name')}
          </p>
        </div>
      </div>

      <p className="text-sm text-muted-foreground leading-relaxed">
        {t('overview.description')}
      </p>

      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link to="/chat">{t('nav.chat')}</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/experts">{t('nav.experts')}</Link>
        </Button>
        {canCreate && (
          <Button asChild variant="outline">
            <Link to="/experts/new">{t('experts.create')}</Link>
          </Button>
        )}
        <Button asChild variant="outline">
          <Link to="/members">{t('nav.members')}</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/storage">{t('nav.storage')}</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/settings">{t('nav.settings')}</Link>
        </Button>
      </div>

      <OverviewUsageSummary />

      {/* Experts quick-access */}
      {experts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('overview.expertsTitle')}</CardTitle>
            <CardDescription>{t('overview.expertsDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {experts.map((expert) => (
              <ExpertCard key={expert.id} expert={expert} />
            ))}
          </CardContent>
        </Card>
      )}

      <OverviewRecommendedApps />
    </div>
  );
}
