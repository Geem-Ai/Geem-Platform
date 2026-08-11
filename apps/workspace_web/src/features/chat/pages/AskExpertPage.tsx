import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from '@/features/workspaces/WorkspaceProvider';
import type { Expert } from '@/services/api/types';
import { loadLastExpert, saveLastExpert } from '@/features/experts/lib/last-expert';
import { useExperts } from '@/features/experts/hooks/useExperts';
import { ChatShell } from '../components/ChatShell';
import { ExpertSelector } from '../components/ExpertSelector';

export function AskExpertPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? '';

  const expertsQuery = useExperts();
  const allExperts: Expert[] = useMemo(
    () => expertsQuery.data ?? [],
    [expertsQuery.data],
  );

  const expertIdParam = searchParams.get('expert');
  const [selectedExpertId, setSelectedExpertId] = useState<string | null>(expertIdParam);
  const [invalidDeepLink, setInvalidDeepLink] = useState(false);

  useEffect(() => {
    setSelectedExpertId(expertIdParam);
    setInvalidDeepLink(false);
  }, [expertIdParam, workspaceId]);

  // Validate deep link / restore last expert against the current workspace list.
  useEffect(() => {
    if (expertsQuery.isLoading || !workspaceId) return;

    if (selectedExpertId) {
      const found = allExperts.some((e) => e.id === selectedExpertId);
      if (!found) {
        setInvalidDeepLink(Boolean(expertIdParam));
        setSelectedExpertId(null);
        if (expertIdParam) {
          setSearchParams({}, { replace: true });
        }
      }
      return;
    }

    if (expertIdParam) return;
    const last = loadLastExpert(workspaceId);
    if (last && allExperts.some((e) => e.id === last)) {
      setSelectedExpertId(last);
      setSearchParams({ expert: last }, { replace: true });
    }
  }, [
    allExperts,
    expertIdParam,
    expertsQuery.isLoading,
    selectedExpertId,
    setSearchParams,
    workspaceId,
  ]);

  function handleSelectExpert(id: string) {
    setInvalidDeepLink(false);
    setSelectedExpertId(id);
    setSearchParams({ expert: id }, { replace: true });
    if (workspaceId) saveLastExpert(workspaceId, id);
  }

  const selectedExpert = selectedExpertId
    ? allExperts.find((e) => e.id === selectedExpertId) ?? null
    : null;

  return (
    <div className="flex h-full min-h-[60vh]">
      <Helmet>
        <title>
          {selectedExpert ? `${selectedExpert.name} · ` : ''}
          {t('chat.title')} · {t('app.name')}
        </title>
      </Helmet>

      <div className="w-72 shrink-0 border-e border-border overflow-y-auto p-4 hidden md:block">
        <h2 className="text-sm font-semibold mb-3">{t('chat.selectExpert')}</h2>
        <ExpertSelector
          experts={allExperts}
          selectedId={selectedExpertId}
          onSelect={handleSelectExpert}
          isLoading={expertsQuery.isLoading}
        />
      </div>

      <div className="flex-1 min-w-0 flex flex-col">
        {selectedExpert ? (
          <ChatShell expert={selectedExpert} workspaceId={workspaceId} />
        ) : (
          <div className="flex h-full items-center justify-center text-center p-6">
            <div className="space-y-2 max-w-sm">
              <h1 className="text-xl font-semibold">{t('chat.title')}</h1>
              {invalidDeepLink ? (
                <p className="text-sm text-muted-foreground">{t('chat.expertNotFoundHint')}</p>
              ) : (
                <p className="text-sm text-muted-foreground">{t('chat.selectExpertHint')}</p>
              )}
              <div className="md:hidden mt-4">
                <ExpertSelector
                  experts={allExperts}
                  selectedId={selectedExpertId}
                  onSelect={handleSelectExpert}
                  isLoading={expertsQuery.isLoading}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
