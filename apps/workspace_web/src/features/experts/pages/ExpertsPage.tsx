import { Link, useNavigate } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import type { Expert } from '@/services/api/types';
import { canCreateExpert } from '../lib/capabilities';
import { useExperts } from '../hooks/useExperts';
import { ExpertListSection } from '../components/ExpertListSection';

export function ExpertsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { currentMembership, currentWorkspace } = useWorkspace();
  const role = currentMembership?.role ?? currentWorkspace?.role;
  const canCreate = canCreateExpert(role);

  const expertsQuery = useExperts();

  const allExperts: Expert[] = expertsQuery.data ?? [];
  const workspaceExperts = allExperts.filter((e) => e.ownership === 'workspace');
  const platformExperts = allExperts.filter((e) => e.ownership === 'platform');

  function handleAsk(expert: Expert) {
    void navigate(`/chat?expert=${expert.id}`);
  }

  return (
    <div className="p-6 md:p-8 w-full max-w-3xl space-y-6 ms-auto me-auto">
      <Helmet>
        <title>
          {t('experts.title')} · {t('app.name')}
        </title>
      </Helmet>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t('experts.title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('experts.description')}</p>
        </div>
        {canCreate && (
          <Button asChild>
            <Link to="/experts/new">{t('experts.create')}</Link>
          </Button>
        )}
      </div>

      {expertsQuery.isLoading && (
        <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>
      )}
      {expertsQuery.isError && (
        <p className="text-sm text-destructive">{t('errors.generic')}</p>
      )}

      {!expertsQuery.isLoading && !expertsQuery.isError && (
        <div className="space-y-8">
          <ExpertListSection
            titleKey="experts.myExperts"
            experts={workspaceExperts}
            onAsk={handleAsk}
            emptyKey={canCreate ? 'experts.noExpertsHint' : 'experts.noExpertsMember'}
          />
          <ExpertListSection
            titleKey="experts.platformExperts"
            experts={platformExperts}
            onAsk={handleAsk}
            emptyKey="experts.noPlatformExperts"
          />
        </div>
      )}
    </div>
  );
}
