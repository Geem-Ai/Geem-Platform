import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { WorkspaceKindBadge, WorkspaceStatusBadge } from '@/components/shared/StatusBadges';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformWorkspaces, platformQueryKeys } from '@/services/api/platform';

const PAGE_SIZE = 25;

export function WorkspacesPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('tenant');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      kind: kind || 'tenant',
    }),
    [offset, search, status, kind],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.workspaces(filters),
    queryFn: () => fetchPlatformWorkspaces(filters),
  });

  const onSearchChange = (value: string) => {
    setSearch(value);
    setOffset(0);
  };

  return (
    <div className="space-y-4" data-testid="workspaces-page">
      <DocumentTitle title={t('workspaces.title')} />
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('workspaces.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('workspaces.subtitle')}</p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('workspaces.listTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <AdminListFilters
            search={search}
            onSearchChange={onSearchChange}
            searchPlaceholderKey="workspaces.searchPlaceholder"
            status={status}
            onStatusChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
            statusOptions={[
              { value: 'active', labelKey: 'status.workspace.active' },
              { value: 'suspended', labelKey: 'status.workspace.suspended' },
              { value: 'archived', labelKey: 'status.workspace.archived' },
            ]}
            secondary={kind}
            onSecondaryChange={(v) => {
              setKind(v);
              setOffset(0);
            }}
            secondaryOptions={[
              { value: 'all', labelKey: 'common.all' },
              { value: 'tenant', labelKey: 'status.kind.tenant' },
              { value: 'system', labelKey: 'status.kind.system' },
            ]}
            secondaryLabelKey="workspaces.kind"
            secondaryIncludeBlank={false}
            testIdPrefix="workspaces"
          />

          {query.isLoading ? (
            <div className="space-y-3" data-testid="workspaces-loading">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : null}

          {query.isError ? (
            <p className="text-sm text-destructive py-6" data-testid="workspaces-error">
              {getErrorMessage(query.error, t)}
            </p>
          ) : null}

          {query.isSuccess && query.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8" data-testid="workspaces-empty">
              {t('workspaces.empty')}
            </p>
          ) : null}

          {query.isSuccess && query.data.items.length > 0 ? (
            <>
              <ul className="divide-y divide-border rounded-md border" data-testid="workspaces-list">
                {query.data.items.map((ws) => (
                  <li key={ws.id}>
                    <Link
                      to={`/workspaces/${ws.id}`}
                      className="flex flex-col gap-2 p-4 hover:bg-muted/40 sm:flex-row sm:items-center sm:justify-between"
                      data-testid="workspace-row"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="truncate font-medium text-sm">{ws.name}</p>
                        <p className="truncate text-xs text-muted-foreground font-mono">{ws.slug}</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <WorkspaceStatusBadge status={ws.status} />
                        <WorkspaceKindBadge kind={ws.kind} />
                        <span data-testid="workspace-members-count">
                          {t('workspaces.membersCount', { count: ws.members_count })}
                        </span>
                        {ws.current_plan_name ? (
                          <span className="hidden sm:inline">{ws.current_plan_name}</span>
                        ) : null}
                        <span className="tabular-nums">
                          {formatAdminDate(ws.created_at, i18n.language)}
                        </span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              <AdminPagination
                total={query.data.total}
                limit={query.data.limit}
                offset={query.data.offset}
                onPageChange={setOffset}
                testId="workspaces-pagination"
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
