import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { RefreshCw, ScrollText } from 'lucide-react';
import { AdminPagination } from '@/components/shared/AdminPagination';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { formatAdminDateTime } from '@/lib/dates';
import { cn } from '@/lib/utils';
import { getErrorMessage } from '@/services/api/errors';
import {
  fetchPlatformAuditLog,
  fetchPlatformAuditLogs,
  platformQueryKeys,
} from '@/services/api/platform';
import type { PlatformAuditListItem } from '@/services/api/types';

const PAGE_SIZE = 25;

function auditActionLabel(action: string, t: (key: string) => string): string {
  const key = `audit.actions.${action}`;
  const translated = t(key);
  return translated === key ? action : translated;
}

function resourceLink(item: PlatformAuditListItem): string | null {
  const type = item.resource.entity_type;
  const id = item.resource.entity_id;
  if (!id) return null;
  if (type === 'workspace') return `/workspaces/${id}`;
  if (type === 'user') return `/users/${id}`;
  if (type === 'plan') return `/plans/${id}`;
  if (type === 'expert') return `/experts/${id}`;
  if (type === 'catalog_app') return `/app-store/${id}`;
  if (type === 'purchase') return `/purchases/${id}`;
  return null;
}

export function AuditLogsPage() {
  const { t, i18n } = useTranslation();
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filters = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset,
      search: search || undefined,
    }),
    [offset, search],
  );

  const listQuery = useQuery({
    queryKey: platformQueryKeys.auditLogs(filters),
    queryFn: () => fetchPlatformAuditLogs(filters),
    staleTime: 30_000,
  });

  const detailQuery = useQuery({
    queryKey: platformQueryKeys.auditLog(selectedId ?? ''),
    queryFn: () => fetchPlatformAuditLog(selectedId!),
    enabled: Boolean(selectedId),
  });

  const items = listQuery.data?.items ?? [];

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6 md:p-8" data-testid="audit-logs-page">
      <DocumentTitle title={t('audit.title')} />
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{t('audit.eyebrow')}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{t('audit.title')}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{t('audit.subtitle')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void listQuery.refetch()} disabled={listQuery.isFetching}>
          <RefreshCw className={cn('size-4', listQuery.isFetching && 'animate-spin')} aria-hidden />
          {t('common.refresh')}
        </Button>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="audit-search">
            {t('common.search')}
          </label>
          <input
            id="audit-search"
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
            placeholder={t('audit.searchPlaceholder')}
            data-testid="audit-search"
          />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ScrollText className="size-4" aria-hidden />
            {t('audit.listTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {listQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : null}
          {listQuery.isError ? (
            <p className="text-sm text-destructive">{getErrorMessage(listQuery.error, t)}</p>
          ) : null}
          {items.length === 0 && !listQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t('audit.empty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr className="border-b border-border text-start text-muted-foreground">
                    <th className="px-2 py-2 font-medium">{t('audit.columns.time')}</th>
                    <th className="px-2 py-2 font-medium">{t('audit.columns.actor')}</th>
                    <th className="px-2 py-2 font-medium">{t('audit.columns.action')}</th>
                    <th className="px-2 py-2 font-medium">{t('audit.columns.workspace')}</th>
                    <th className="px-2 py-2 font-medium">{t('audit.columns.resource')}</th>
                    <th className="px-2 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} className="border-b border-border/70">
                      <td className="px-2 py-3">{formatAdminDateTime(item.created_at, i18n.language)}</td>
                      <td className="px-2 py-3">{item.actor?.email ?? t('audit.systemActor')}</td>
                      <td className="px-2 py-3">{auditActionLabel(item.action, t)}</td>
                      <td className="px-2 py-3">
                        {item.workspace?.name ?? t('audit.platformScope')}
                      </td>
                      <td className="px-2 py-3">
                        {item.resource.entity_type}
                        {item.resource.entity_id ? ` · ${item.resource.entity_id.slice(0, 8)}…` : ''}
                      </td>
                      <td className="px-2 py-3 text-end">
                        <Button size="sm" variant="outline" onClick={() => setSelectedId(item.id)}>
                          {t('audit.viewDetails')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <AdminPagination
            offset={offset}
            limit={PAGE_SIZE}
            total={listQuery.data?.total ?? 0}
            onPageChange={setOffset}
          />
        </CardContent>
      </Card>

      <Sheet open={Boolean(selectedId)} onOpenChange={(open) => !open && setSelectedId(null)}>
        <SheetContent className="overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>{t('audit.detailTitle')}</SheetTitle>
            <SheetDescription>{detailQuery.data?.action}</SheetDescription>
          </SheetHeader>
          {detailQuery.isLoading ? (
            <p className="mt-4 text-sm text-muted-foreground">{t('common.loading')}</p>
          ) : null}
          {detailQuery.data ? (
            <div className="mt-4 space-y-4 text-sm">
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.columns.time')}</p>
                <p>{formatAdminDateTime(detailQuery.data.created_at, i18n.language)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.columns.actor')}</p>
                <p>{detailQuery.data.actor?.email ?? t('audit.systemActor')}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.columns.action')}</p>
                <p>{auditActionLabel(detailQuery.data.action, t)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.columns.workspace')}</p>
                <p>{detailQuery.data.workspace?.name ?? t('audit.platformScope')}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('audit.columns.resource')}</p>
                <p>
                  {detailQuery.data.resource.entity_type}
                  {detailQuery.data.resource.entity_id
                    ? ` (${detailQuery.data.resource.entity_id})`
                    : ''}
                </p>
                {(() => {
                  const href = resourceLink(detailQuery.data);
                  return href ? (
                    <Link to={href} className="text-primary hover:underline">
                      {t('audit.openResource')}
                    </Link>
                  ) : null;
                })()}
              </div>
              {detailQuery.data.summary ? (
                <div>
                  <p className="text-xs text-muted-foreground">{t('audit.summary')}</p>
                  <p>{detailQuery.data.summary}</p>
                </div>
              ) : null}
              <div>
                <p className="mb-2 text-xs text-muted-foreground">{t('audit.metadata')}</p>
                <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">
                  {JSON.stringify(detailQuery.data.metadata, null, 2)}
                </pre>
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
