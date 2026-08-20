import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { PlatformRoleBadge, UserStatusBadge } from '@/components/shared/StatusBadges';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformUsers, platformQueryKeys } from '@/services/api/platform';

const PAGE_SIZE = 25;

export function UsersPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [platformRole, setPlatformRole] = useState('');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
      platform_role: platformRole || undefined,
    }),
    [offset, search, status, platformRole],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.users(filters),
    queryFn: () => fetchPlatformUsers(filters),
  });

  return (
    <div className="space-y-4" data-testid="users-page">
      <DocumentTitle title={t('users.title')} />
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t('users.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('users.subtitle')}</p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('users.listTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <AdminListFilters
            search={search}
            onSearchChange={(v) => {
              setSearch(v);
              setOffset(0);
            }}
            searchPlaceholderKey="users.searchPlaceholder"
            status={status}
            onStatusChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
            statusOptions={[
              { value: 'active', labelKey: 'status.user.active' },
              { value: 'disabled', labelKey: 'status.user.disabled' },
            ]}
            secondary={platformRole}
            onSecondaryChange={(v) => {
              setPlatformRole(v);
              setOffset(0);
            }}
            secondaryOptions={[
              { value: 'admin', labelKey: 'status.platformRole.admin' },
              { value: 'none', labelKey: 'status.platformRole.none' },
            ]}
            secondaryLabelKey="users.platformRole"
            testIdPrefix="users"
          />

          {query.isLoading ? (
            <div className="space-y-3" data-testid="users-loading">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : null}

          {query.isError ? (
            <p className="text-sm text-destructive py-6" data-testid="users-error">
              {getErrorMessage(query.error, t)}
            </p>
          ) : null}

          {query.isSuccess && query.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8" data-testid="users-empty">
              {t('users.empty')}
            </p>
          ) : null}

          {query.isSuccess && query.data.items.length > 0 ? (
            <>
              <ul className="divide-y divide-border rounded-md border" data-testid="users-list">
                {query.data.items.map((u) => (
                  <li key={u.id}>
                    <Link
                      to={`/users/${u.id}`}
                      className="flex flex-col gap-2 p-4 hover:bg-muted/40 sm:flex-row sm:items-center sm:justify-between"
                      data-testid="user-row"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-sm">{u.email}</p>
                        <p className="text-xs text-muted-foreground">
                          {t('users.workspacesCount', { count: u.workspace_memberships_count })}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <UserStatusBadge status={u.status} />
                        <PlatformRoleBadge role={u.platform_role} />
                        <span className="tabular-nums">
                          {formatAdminDate(u.created_at, i18n.language)}
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
                testId="users-pagination"
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
