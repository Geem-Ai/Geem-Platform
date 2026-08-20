import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { AdminListFilters } from '@/components/shared/AdminListFilters';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { PlanStatusBadge } from '@/components/shared/StatusBadges';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatAdminDate } from '@/lib/dates';
import { formatMoney } from '@/lib/format';
import { getErrorMessage } from '@/services/api/errors';
import { fetchPlatformPlans, platformQueryKeys } from '@/services/api/platform';

const PAGE_SIZE = 25;

export function PlansPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
      status: status || undefined,
    }),
    [offset, search, status],
  );

  const query = useQuery({
    queryKey: platformQueryKeys.plans(filters),
    queryFn: () => fetchPlatformPlans(filters),
  });

  return (
    <div className="space-y-4" data-testid="plans-page">
      <DocumentTitle title={t('plans.title')} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t('plans.title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('plans.subtitle')}</p>
        </div>
        <Button asChild data-testid="plans-create-button">
          <Link to="/plans/new">{t('plans.create')}</Link>
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('plans.listTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <AdminListFilters
            search={search}
            onSearchChange={(v) => {
              setSearch(v);
              setOffset(0);
            }}
            searchPlaceholderKey="plans.searchPlaceholder"
            status={status}
            onStatusChange={(v) => {
              setStatus(v);
              setOffset(0);
            }}
            statusOptions={[
              { value: 'active', labelKey: 'status.plan.active' },
              { value: 'archived', labelKey: 'status.plan.archived' },
            ]}
            testIdPrefix="plans"
          />

          {query.isLoading ? (
            <div className="space-y-3" data-testid="plans-loading">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : null}

          {query.isError ? (
            <p className="text-sm text-destructive py-6" data-testid="plans-error">
              {getErrorMessage(query.error, t)}
            </p>
          ) : null}

          {query.isSuccess && query.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8" data-testid="plans-empty">
              {t('plans.empty')}
            </p>
          ) : null}

          {query.isSuccess && query.data.items.length > 0 ? (
            <>
              <ul className="divide-y divide-border rounded-md border" data-testid="plans-list">
                {query.data.items.map((plan) => (
                  <li key={plan.id}>
                    <Link
                      to={`/plans/${plan.id}`}
                      className="flex flex-col gap-2 p-4 hover:bg-muted/40 sm:flex-row sm:items-center sm:justify-between"
                      data-testid="plan-row"
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate font-medium text-sm">{plan.name}</p>
                          {plan.is_bootstrap ? (
                            <Badge variant="info" appearance="light" size="sm" data-testid="plan-bootstrap-badge">
                              {t('plans.bootstrap')}
                            </Badge>
                          ) : null}
                        </div>
                        <p className="truncate text-xs text-muted-foreground font-mono">{plan.code}</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <PlanStatusBadge status={plan.status} />
                        <span data-testid="plan-price">
                          {formatMoney(plan.price_amount, plan.currency)}
                        </span>
                        <span data-testid="plan-subscribers">
                          {t('plans.subscribers', { count: plan.subscriber_count })}
                        </span>
                        <span className="tabular-nums">
                          {formatAdminDate(plan.updated_at, i18n.language)}
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
                testId="plans-pagination"
              />
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
