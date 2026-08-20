import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { GrantCreditsDialog } from '@/features/credits/components/GrantCreditsDialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDateTime } from '@/lib/dates';
import { formatInteger } from '@/lib/format';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformWorkspaces,
  fetchWorkspaceCreditHistory,
  fetchWorkspaceCredits,
  platformQueryKeys,
} from '@/services/api/platform';

const PAGE_SIZE = 25;
const HISTORY_PAGE = 20;

export function CreditsPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [grantOpen, setGrantOpen] = useState(false);

  const workspaceFilters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: 0,
      search: search || undefined,
      kind: 'tenant',
    }),
    [search],
  );

  const workspacesQuery = useQuery({
    queryKey: platformQueryKeys.workspaces(workspaceFilters),
    queryFn: () => fetchPlatformWorkspaces(workspaceFilters),
  });

  const selectedWorkspace = workspacesQuery.data?.items.find((w) => w.id === selectedId);

  const creditsQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCredits(selectedId ?? ''),
    queryFn: () => fetchWorkspaceCredits(selectedId!),
    enabled: Boolean(selectedId),
  });

  const historyFilters = useMemo(
    () => ({ limit: HISTORY_PAGE, offset: historyOffset }),
    [historyOffset],
  );

  const historyQuery = useQuery({
    queryKey: platformQueryKeys.workspaceCreditHistory(selectedId ?? '', historyFilters),
    queryFn: () => fetchWorkspaceCreditHistory(selectedId!, historyFilters),
    enabled: Boolean(selectedId),
  });

  const onGranted = async () => {
    if (!selectedId) return;
    await queryClient.invalidateQueries({
      queryKey: platformQueryKeys.workspaceCredits(selectedId),
    });
    await queryClient.invalidateQueries({
      queryKey: ['platform', 'workspace', selectedId, 'credits', 'history'],
    });
  };

  return (
    <div className="space-y-4" data-testid="credits-page">
      <DocumentTitle title={t('credits.title')} />
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('credits.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('credits.subtitle')}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('credits.selectWorkspace')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <AdminListFilters
              search={search}
              onSearchChange={(v) => {
                setSearch(v);
                setSelectedId(null);
                setHistoryOffset(0);
              }}
              searchPlaceholderKey="workspaces.searchPlaceholder"
              testIdPrefix="credits-workspaces"
            />

            {workspacesQuery.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-muted" />
                ))}
              </div>
            ) : null}

            {workspacesQuery.isError ? (
              <p className="text-sm text-destructive">{getErrorMessage(workspacesQuery.error, t)}</p>
            ) : null}

            {workspacesQuery.isSuccess && workspacesQuery.data.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('credits.noWorkspaces')}</p>
            ) : null}

            {workspacesQuery.isSuccess && workspacesQuery.data.items.length > 0 ? (
              <ul className="divide-y divide-border rounded-md border" data-testid="credits-workspace-list">
                {workspacesQuery.data.items.map((ws) => (
                  <li key={ws.id}>
                    <button
                      type="button"
                      className={`flex w-full flex-col gap-1 p-3 text-start hover:bg-muted/40 ${
                        selectedId === ws.id ? 'bg-muted/60' : ''
                      }`}
                      onClick={() => {
                        setSelectedId(ws.id);
                        setHistoryOffset(0);
                      }}
                      data-testid="credits-workspace-row"
                    >
                      <span className="text-sm font-medium truncate">{ws.name}</span>
                      <span className="text-xs text-muted-foreground font-mono truncate">
                        {ws.slug}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="text-base">{t('credits.balanceCard')}</CardTitle>
              {selectedId ? (
                <Button size="sm" onClick={() => setGrantOpen(true)} data-testid="credits-grant-button">
                  {t('credits.grant')}
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {!selectedId ? (
              <p className="text-sm text-muted-foreground" data-testid="credits-pick-hint">
                {t('credits.pickHint')}
              </p>
            ) : (
              <>
                <div className="space-y-1">
                  <p className="text-sm font-medium">{selectedWorkspace?.name}</p>
                  <Link
                    to={`/workspaces/${selectedId}`}
                    className="text-xs text-muted-foreground hover:underline"
                  >
                    {t('credits.openWorkspace')}
                  </Link>
                </div>

                {creditsQuery.isLoading ? (
                  <div className="h-16 animate-pulse rounded bg-muted" />
                ) : creditsQuery.isError ? (
                  <p className="text-sm text-destructive">{getErrorMessage(creditsQuery.error, t)}</p>
                ) : (
                  <p className="text-2xl font-semibold tabular-nums" data-testid="credits-balance">
                    {formatInteger(creditsQuery.data?.balance ?? 0, i18n.language)}
                  </p>
                )}

                <div className="space-y-2">
                  <h3 className="text-sm font-medium">{t('credits.history')}</h3>
                  {historyQuery.isLoading ? (
                    <div className="h-20 animate-pulse rounded bg-muted" />
                  ) : historyQuery.isError ? (
                    <p className="text-sm text-destructive">
                      {getErrorMessage(historyQuery.error, t)}
                    </p>
                  ) : historyQuery.data?.items.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t('credits.historyEmpty')}</p>
                  ) : (
                    <>
                      <ul className="divide-y divide-border rounded-md border" data-testid="credits-history-list">
                        {historyQuery.data?.items.map((entry) => (
                          <li
                            key={entry.id}
                            className="flex flex-col gap-1 p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
                            data-testid="credits-history-row"
                          >
                            <div className="min-w-0">
                              <p className="font-medium">{entry.entry_type}</p>
                              <p className="text-xs text-muted-foreground truncate">
                                {entry.reason || t('common.none')}
                              </p>
                            </div>
                            <div className="text-xs text-muted-foreground text-end">
                              <p className="tabular-nums text-sm text-foreground">
                                {entry.amount > 0 ? '+' : ''}
                                {formatInteger(entry.amount, i18n.language)}
                              </p>
                              <p>{formatAdminDateTime(entry.created_at, i18n.language)}</p>
                            </div>
                          </li>
                        ))}
                      </ul>
                      {historyQuery.data ? (
                        <AdminPagination
                          total={historyQuery.data.total}
                          limit={historyQuery.data.limit}
                          offset={historyQuery.data.offset}
                          onPageChange={setHistoryOffset}
                          testId="credits-history-pagination"
                        />
                      ) : null}
                    </>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {selectedId ? (
        <GrantCreditsDialog
          open={grantOpen}
          onOpenChange={setGrantOpen}
          workspaceId={selectedId}
          onGranted={onGranted}
        />
      ) : null}
    </div>
  );
}
