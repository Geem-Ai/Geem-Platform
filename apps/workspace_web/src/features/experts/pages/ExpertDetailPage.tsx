import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { canAskExpert, canDeleteExpert, canEditExpert, canManageExpertKnowledge } from '../lib/capabilities';
import { useExpert } from '../hooks/useExpert';
import { useExpertKnowledge } from '../hooks/useExpertKnowledge';
import { useDeleteExpert } from '../hooks/useExpertMutations';
import { ExpertStatusBadge } from '../components/ExpertStatusBadge';
import { KnowledgeSourcesPanel } from '../components/KnowledgeSourcesPanel';
import { DeleteExpertDialog } from '../components/DeleteExpertDialog';

export function ExpertDetailPage() {
  const { t } = useTranslation();
  const { expertId } = useParams<{ expertId: string }>();
  const navigate = useNavigate();
  const { currentMembership, currentWorkspace } = useWorkspace();
  const role = currentMembership?.role ?? currentWorkspace?.role;

  const expertQuery = useExpert(expertId);
  const expert = expertQuery.data;
  const knowledgeQuery = useExpertKnowledge(
    expert?.ownership === 'workspace' ? expertId : undefined,
  );

  const deleteMutation = useDeleteExpert();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const canEdit = expert ? canEditExpert(role, expert.ownership) : false;
  const canDelete = expert ? canDeleteExpert(role, expert.ownership) : false;
  const canManageKnowledge = expert ? canManageExpertKnowledge(role, expert.ownership) : false;
  const canAsk = expert ? canAskExpert(expert.status) : false;

  function handleDelete() {
    if (!expert) return;
    deleteMutation.mutate(expert.id, {
      onSuccess: () => {
        toast.success(t('experts.deleted'));
        void navigate('/experts');
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(t(errorMessageKey(err.code)));
        } else {
          toast.error(t('errors.generic'));
        }
        setDeleteOpen(false);
      },
    });
  }

  if (expertQuery.isLoading) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>
      </div>
    );
  }

  if (expertQuery.isError || !expert) {
    return (
      <div className="p-8">
        <p className="text-sm text-destructive">{t('errors.expertNotFound')}</p>
        <Button asChild variant="outline" className="mt-4">
          <Link to="/experts">{t('experts.title')}</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 w-full max-w-3xl space-y-6 ms-auto me-auto">
      <Helmet>
        <title>
          {expert.name} · {t('app.name')}
        </title>
      </Helmet>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          {expert.icon_url ? (
            <img
              src={expert.icon_url}
              alt={expert.name}
              className="size-10 rounded-full shrink-0 object-cover"
            />
          ) : (
            <div className="size-10 rounded-full shrink-0 bg-muted flex items-center justify-center text-base font-semibold text-muted-foreground">
              {expert.name.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight truncate">{expert.name}</h1>
            {expert.description && (
              <p className="text-sm text-muted-foreground">{expert.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <ExpertStatusBadge status={expert.status} />
          {canAsk && (
            <Button asChild size="sm">
              <Link to={`/chat?expert=${expert.id}`}>{t('experts.ask')}</Link>
            </Button>
          )}
          {canEdit && (
            <Button asChild variant="outline" size="sm">
              <Link to={`/experts/${expert.id}/edit`}>{t('experts.edit')}</Link>
            </Button>
          )}
        </div>
      </div>

      {/* Knowledge (workspace experts only) */}
      {expert.ownership === 'workspace' && (
        <Card>
          <CardContent className="pt-4">
            <KnowledgeSourcesPanel
              expertId={expert.id}
              items={knowledgeQuery.data ?? []}
              canManage={canManageKnowledge}
              isLoading={knowledgeQuery.isLoading}
              isError={knowledgeQuery.isError}
            />
          </CardContent>
        </Card>
      )}

      {expert.ownership === 'platform' && (
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">{t('experts.platformManaged')}</p>
          </CardContent>
        </Card>
      )}

      {/* System instructions (workspace experts only — platform redacted by API) */}
      {expert.ownership === 'workspace' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t('experts.instructions')}</CardTitle>
          </CardHeader>
          <CardContent>
            {expert.system_instructions ? (
              <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono">
                {expert.system_instructions}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">{t('experts.knowledgeEmptyHint')}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* RAG config (workspace experts only) */}
      {expert.ownership === 'workspace' && expert.rag_config && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t('experts.advancedSettings')}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-1">
            {expert.rag_config.top_k != null && (
              <p>{t('experts.topK')}: {expert.rag_config.top_k}</p>
            )}
            {expert.rag_config.rerank_top_n != null && (
              <p>{t('experts.rerankTopN')}: {expert.rag_config.rerank_top_n}</p>
            )}
            {expert.rag_config.similarity_threshold != null && (
              <p>{t('experts.similarityThreshold')}: {expert.rag_config.similarity_threshold}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Danger zone */}
      {canDelete && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-sm text-destructive">{t('experts.dangerZone')}</CardTitle>
          </CardHeader>
          <CardContent>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDeleteOpen(true)}
            >
              {t('experts.deleteTitle')}
            </Button>
          </CardContent>
        </Card>
      )}

      {canDelete && expert && (
        <DeleteExpertDialog
          expert={expert}
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          onConfirm={handleDelete}
          isPending={deleteMutation.isPending}
        />
      )}
    </div>
  );
}
