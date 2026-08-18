import { useMemo, useState } from 'react';
import { useNavigate, useParams, useMatch } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus, RefreshCw, Search, Sparkles } from 'lucide-react';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { usePermissions } from '@/features/authz/usePermissions';
import type { Expert } from '@/services/api/types';
import { canCreateExpert } from '../lib/capabilities';
import { localizeExpertDisplay } from '../lib/localize';
import { useExperts } from '../hooks/useExperts';
import { ExpertDetailSheet } from '../components/ExpertDetailSheet';
import { ExpertFormSheet } from '../components/ExpertFormSheet';
import { ExpertListSection } from '../components/ExpertListSection';

type ExpertsTab = 'workspace' | 'platform';

function ExpertCardSkeleton() {
  return (
    <Card className="shadow-none">
      <CardContent className="p-5 space-y-4">
        <div className="flex gap-3">
          <div className="size-11 rounded-xl bg-muted animate-pulse" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-2/3 rounded bg-muted animate-pulse" />
            <div className="h-3 w-full rounded bg-muted animate-pulse" />
            <div className="h-3 w-4/5 rounded bg-muted animate-pulse" />
          </div>
        </div>
        <div className="h-8 rounded bg-muted animate-pulse" />
      </CardContent>
    </Card>
  );
}

/**
 * Experts list + Metronic-style floating Sheets for create / edit / view.
 */
export function ExpertsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { expertId } = useParams<{ expertId?: string }>();
  const createMatch = useMatch('/experts/new');
  const editMatch = useMatch('/experts/:expertId/edit');
  const viewMatch = useMatch('/experts/:expertId');

  const { can } = usePermissions();
  const canCreate = canCreateExpert(can);

  const expertsQuery = useExperts();
  const allExperts = useMemo(() => expertsQuery.data ?? [], [expertsQuery.data]);

  const [tab, setTab] = useState<ExpertsTab>('workspace');
  const [search, setSearch] = useState('');

  const createOpen = Boolean(createMatch);
  const editOpen = Boolean(editMatch);
  const viewOpen = Boolean(viewMatch) && !editOpen && Boolean(expertId);
  const activeExpertId = expertId;

  const query = search.trim().toLowerCase();

  function matchesExpertSearch(e: Expert): boolean {
    if (!query) return true;
    const display = localizeExpertDisplay(e, t);
    return (
      display.name.toLowerCase().includes(query) ||
      (display.description ?? '').toLowerCase().includes(query) ||
      e.name.toLowerCase().includes(query) ||
      (e.description ?? '').toLowerCase().includes(query)
    );
  }

  const workspaceExperts = useMemo(
    () =>
      allExperts.filter((e) => e.ownership === 'workspace' && matchesExpertSearch(e)),
    [allExperts, query, t],
  );

  const platformExperts = useMemo(
    () =>
      allExperts.filter((e) => e.ownership === 'platform' && matchesExpertSearch(e)),
    [allExperts, query, t],
  );

  const workspaceCount = allExperts.filter((e) => e.ownership === 'workspace').length;
  const platformCount = allExperts.filter((e) => e.ownership === 'platform').length;
  const visibleExperts = tab === 'workspace' ? workspaceExperts : platformExperts;

  const activeExpert = useMemo(
    () => allExperts.find((e) => e.id === activeExpertId) ?? null,
    [allExperts, activeExpertId],
  );
  const activeExpertName = activeExpert
    ? localizeExpertDisplay(activeExpert, t).name
    : null;
  const documentTitle = createOpen
    ? t('experts.createTitle')
    : editOpen
      ? t('experts.editTitle')
      : viewOpen
        ? (activeExpertName ?? t('experts.title'))
        : t('experts.title');

  function closeSheets() {
    void navigate('/experts');
  }

  function handleAsk(expert: Expert) {
    void navigate(`/chat?expert=${expert.id}`);
  }

  function handleOpen(expert: Expert) {
    void navigate(`/experts/${expert.id}`);
  }

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-6xl space-y-6 ms-auto me-auto">
      <DocumentTitle title={documentTitle} />

      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="size-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Sparkles className="size-4" aria-hidden />
            </div>
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
              {t('experts.title')}
            </h1>
          </div>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            {t('experts.description')}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => void navigate('/experts/new')} className="shrink-0 self-start">
            <Plus className="size-4" />
            {t('experts.create')}
          </Button>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div
          role="tablist"
          aria-label={t('experts.title')}
          className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'workspace'}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
              tab === 'workspace'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setTab('workspace')}
          >
            {t('experts.myExperts')}
            <span className="ms-1.5 tabular-nums text-muted-foreground">
              {workspaceCount}
            </span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'platform'}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
              tab === 'platform'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => setTab('platform')}
          >
            {t('experts.platformExperts')}
            <span className="ms-1.5 tabular-nums text-muted-foreground">
              {platformCount}
            </span>
          </button>
        </div>

        <div className="relative w-full sm:max-w-xs">
          <Search
            className="absolute start-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none"
            aria-hidden
          />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('experts.searchPlaceholder')}
            className="ps-8"
            aria-label={t('experts.searchPlaceholder')}
          />
        </div>
      </div>

      {/* States */}
      {expertsQuery.isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <ExpertCardSkeleton />
          <ExpertCardSkeleton />
          <ExpertCardSkeleton />
        </div>
      )}

      {expertsQuery.isError && (
        <Card className="border-destructive/30">
          <CardContent className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-6">
            <div>
              <p className="text-sm font-medium">{t('experts.loadErrorTitle')}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {t('experts.loadErrorHint')}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void expertsQuery.refetch()}
            >
              <RefreshCw className="size-3.5" />
              {t('experts.retry')}
            </Button>
          </CardContent>
        </Card>
      )}

      {!expertsQuery.isLoading && !expertsQuery.isError && (
        <>
          {query && visibleExperts.length === 0 ? (
            <Card className="border-dashed shadow-none">
              <CardContent className="py-10 text-center space-y-1">
                <p className="text-sm font-medium">{t('experts.searchEmptyTitle')}</p>
                <p className="text-xs text-muted-foreground">
                  {t('experts.searchEmptyHint', { query: search.trim() })}
                </p>
              </CardContent>
            </Card>
          ) : tab === 'workspace' ? (
            <ExpertListSection
              titleKey="experts.myExperts"
              descriptionKey="experts.myExpertsHint"
              experts={workspaceExperts}
              onAsk={handleAsk}
              onOpen={handleOpen}
              emptyTitleKey="experts.noExperts"
              emptyKey={
                canCreate ? 'experts.noExpertsHint' : 'experts.noExpertsMember'
              }
              showCreateInEmpty={canCreate}
              onCreate={() => void navigate('/experts/new')}
            />
          ) : (
            <ExpertListSection
              titleKey="experts.platformExperts"
              descriptionKey="experts.platformExpertsHint"
              experts={platformExperts}
              onAsk={handleAsk}
              onOpen={handleOpen}
              emptyTitleKey="experts.noPlatformExperts"
              emptyKey="experts.noPlatformExpertsHint"
            />
          )}
        </>
      )}

      <ExpertFormSheet
        mode="create"
        open={createOpen}
        onOpenChange={(open) => {
          if (!open) closeSheets();
        }}
        onCreated={(id) => {
          void navigate(`/experts/${id}`);
        }}
      />

      <ExpertFormSheet
        mode="edit"
        open={editOpen}
        expertId={activeExpertId}
        onOpenChange={(open) => {
          if (!open) {
            if (activeExpertId) void navigate(`/experts/${activeExpertId}`);
            else closeSheets();
          }
        }}
        onSaved={(id) => {
          void navigate(`/experts/${id}`);
        }}
      />

      <ExpertDetailSheet
        expertId={activeExpertId}
        open={viewOpen}
        onOpenChange={(open) => {
          if (!open) closeSheets();
        }}
        onEdit={(id) => {
          void navigate(`/experts/${id}/edit`);
        }}
        onDeleted={closeSheets}
      />
    </div>
  );
}
