import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowUpRight,
  HardDrive,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { DocumentTitle } from '@/components/shared/DocumentTitle';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTitle,
  CardToolbar,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { usePermissions } from '@/features/authz/usePermissions';
import { WorkspacePermission } from '@/features/authz/permissions';
import { QuotaAlert } from '@/features/usage/components/QuotaAlert';
import { QuotaMeter } from '@/features/usage/components/QuotaMeter';
import { useUsageSummary } from '@/features/usage/hooks/useUsageQueries';
import { meterWarningLevel } from '@/features/usage/lib/quota';
import type { Meter } from '@/services/api/usage';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import type { DocumentSummary } from '@/services/api/types';
import { cn } from '@/lib/utils';
import { triggerBrowserDownload } from '@/lib/download';
import { DeleteStorageFileDialog } from '../components/DeleteStorageFileDialog';
import { StorageFileList } from '../components/StorageFileList';
import { StoragePagination } from '../components/StoragePagination';
import {
  useDeleteStorageDocument,
  useDownloadStorageDocument,
  useStorageDocuments,
} from '../hooks/useStorageQueries';
import { parseStoragePage, STORAGE_PAGE_SIZE } from '../lib/page';

function StorageSkeleton() {
  return (
    <div className="space-y-6" data-testid="storage-loading">
      <Card className="shadow-xs">
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="h-4 w-28 rounded bg-muted animate-pulse" />
            <div className="h-5 w-16 rounded-full bg-muted animate-pulse" />
          </div>
          <div className="h-8 w-40 rounded bg-muted animate-pulse" />
          <div className="h-2 w-full rounded bg-muted animate-pulse" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-10 rounded bg-muted animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
      <Card className="shadow-xs">
        <CardContent className="p-0">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="px-5 py-4 flex items-start gap-3 border-t first:border-t-0 border-border"
            >
              <div className="size-10 rounded-lg bg-muted animate-pulse shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-2/3 rounded bg-muted animate-pulse" />
                <div className="h-3 w-1/2 rounded bg-muted animate-pulse" />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export function StoragePage() {
  const { t } = useTranslation();
  const { can } = usePermissions();
  const canDelete = can(WorkspacePermission.STORAGE_DELETE);
  const canDownload = can(WorkspacePermission.STORAGE_DOWNLOAD);
  const [params, setParams] = useSearchParams();
  const page = parseStoragePage(params.get('page'));
  const q = params.get('q') ?? '';
  const [search, setSearch] = useState(q);
  const [deleteTarget, setDeleteTarget] = useState<DocumentSummary | null>(null);

  useEffect(() => {
    setSearch(q);
  }, [q]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const next = search.trim();
      if (next === q) return;
      setParams(
        (current) => {
          const nextParams = new URLSearchParams(current);
          if (next) nextParams.set('q', next);
          else nextParams.delete('q');
          nextParams.delete('page');
          return nextParams;
        },
        { replace: true },
      );
    }, 300);
    return () => window.clearTimeout(handle);
  }, [search, q, setParams]);

  const docsQuery = useStorageDocuments({ page, q });
  const usageQuery = useUsageSummary();
  const remove = useDeleteStorageDocument();
  const download = useDownloadStorageDocument();

  const items = docsQuery.data?.items ?? [];
  const total = docsQuery.data?.total ?? 0;
  const summary = usageQuery.data;
  const storageMeter: Meter | null = summary
    ? {
        limit: summary.storage.limit_bytes,
        used: summary.storage.used_bytes,
        reserved: summary.storage.reserved_bytes,
        remaining: summary.storage.remaining_bytes,
        period_start: summary.storage_bytes.period_start,
        period_end: summary.storage_bytes.period_end,
      }
    : null;
  const storageLevel = storageMeter ? meterWarningLevel(storageMeter) : 'normal';
  const refreshing = docsQuery.isFetching || usageQuery.isFetching;

  function clearSearch() {
    setSearch('');
    setParams(
      (current) => {
        const nextParams = new URLSearchParams(current);
        nextParams.delete('q');
        nextParams.delete('page');
        return nextParams;
      },
      { replace: true },
    );
  }

  function handleDelete(item: DocumentSummary) {
    remove.mutate(item.id, {
      onSuccess: () => {
        toast.success(t('storage.deleted'));
        setDeleteTarget(null);
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(t(errorMessageKey(err.code)));
        } else {
          toast.error(t('errors.generic'));
        }
      },
    });
  }

  function handleDownload(item: DocumentSummary) {
    download.mutate(item.id, {
      onSuccess: ({ blob, filename }) => {
        triggerBrowserDownload(blob, filename || item.original_filename);
        toast.success(t('storage.downloaded'));
      },
      onError: (err: unknown) => {
        if (err instanceof ApiError) {
          toast.error(t(errorMessageKey(err.code)));
        } else {
          toast.error(t('storage.downloadFailed'));
        }
      },
    });
  }

  const loading = docsQuery.isLoading || usageQuery.isLoading;

  return (
    <div className="p-4 sm:p-6 md:p-8 w-full max-w-4xl space-y-6 ms-auto me-auto">
      <DocumentTitle title={t('storage.title')} />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            {t('storage.eyebrow')}
          </p>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">
            {t('storage.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
            {t('storage.description')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" asChild>
            <Link to="/experts" data-testid="storage-experts-link">
              <Sparkles className="size-3.5" aria-hidden />
              {t('storage.uploadViaExperts')}
            </Link>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void docsQuery.refetch();
              void usageQuery.refetch();
            }}
            disabled={refreshing}
            data-testid="storage-refresh"
          >
            <RefreshCw
              className={cn('size-3.5', refreshing && 'animate-spin')}
              aria-hidden
            />
            {t('usage.refresh')}
          </Button>
        </div>
      </div>

      {loading ? <StorageSkeleton /> : null}

      {!loading && (docsQuery.isError || usageQuery.isError) ? (
        <Card className="shadow-xs">
          <CardContent className="p-8 text-center space-y-3">
            <div className="size-12 rounded-full bg-destructive/10 text-destructive flex items-center justify-center mx-auto">
              <HardDrive className="size-5" aria-hidden />
            </div>
            <p className="text-sm font-medium">{t('storage.error')}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void docsQuery.refetch();
                void usageQuery.refetch();
              }}
            >
              {t('storage.retry')}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {!loading && !docsQuery.isError && !usageQuery.isError ? (
        <>
          {storageLevel !== 'normal' && storageMeter ? (
            <QuotaAlert
              level={storageLevel}
              code={
                storageLevel === 'exhausted' ? 'storage_quota_exceeded' : undefined
              }
              description={t('storage.quotaHint')}
            />
          ) : null}

          {storageMeter ? (
            <QuotaMeter
              title={t('usage.storage')}
              meter={storageMeter}
              testId="storage-quota-meter"
              format="bytes"
              icon={HardDrive}
            />
          ) : null}

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground leading-relaxed">
              {t('storage.orphanTip')}
            </p>
            <Button mode="link" size="sm" className="h-auto p-0 justify-start" asChild>
              <Link to="/billing/usage" data-testid="storage-usage-link">
                {t('storage.usageLink')}
                <ArrowUpRight className="size-3.5" aria-hidden />
              </Link>
            </Button>
          </div>

          <Card className="shadow-xs overflow-hidden">
            <CardHeader className="min-h-14 py-3 gap-3 flex-nowrap max-sm:flex-wrap">
              <CardHeading className="min-w-0">
                <div className="flex items-center gap-2 min-w-0">
                  <CardTitle className="truncate">{t('storage.filesTitle')}</CardTitle>
                  <Badge
                    variant="secondary"
                    appearance="light"
                    size="sm"
                    className="tabular-nums shrink-0"
                  >
                    {t('storage.fileCount', { count: total })}
                  </Badge>
                </div>
              </CardHeading>
              <CardToolbar className="ms-auto w-full sm:w-auto sm:max-w-xs shrink-0">
                <div className="relative w-full sm:w-56">
                  <Search
                    className="pointer-events-none absolute start-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
                    aria-hidden
                  />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t('storage.searchPlaceholder')}
                    className="h-8 ps-8 pe-8"
                    data-testid="storage-search"
                    aria-label={t('storage.searchPlaceholder')}
                  />
                  {search ? (
                    <button
                      type="button"
                      onClick={clearSearch}
                      className="absolute end-2 top-1/2 -translate-y-1/2 rounded-sm text-muted-foreground hover:text-foreground"
                      aria-label={t('storage.clearSearch')}
                      data-testid="storage-search-clear"
                    >
                      <X className="size-3.5" aria-hidden />
                    </button>
                  ) : null}
                </div>
              </CardToolbar>
            </CardHeader>
            <CardContent className="p-0">
              {items.length === 0 ? (
                <div
                  className="px-6 py-12 text-center space-y-3"
                  data-testid="storage-empty"
                >
                  <div className="size-12 rounded-full bg-muted text-muted-foreground flex items-center justify-center mx-auto">
                    {q.trim() ? (
                      <Search className="size-5" aria-hidden />
                    ) : (
                      <HardDrive className="size-5" aria-hidden />
                    )}
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium">
                      {q.trim() ? t('storage.emptySearch') : t('storage.empty')}
                    </p>
                    {!q.trim() ? (
                      <p className="text-xs text-muted-foreground max-w-sm mx-auto leading-relaxed">
                        {t('storage.emptyHint')}
                      </p>
                    ) : null}
                  </div>
                  {q.trim() ? (
                    <Button variant="outline" size="sm" onClick={clearSearch}>
                      {t('storage.clearSearch')}
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" asChild>
                      <Link to="/experts">{t('storage.uploadViaExperts')}</Link>
                    </Button>
                  )}
                </div>
              ) : (
                <StorageFileList
                  items={items}
                  canDelete={canDelete}
                  canDownload={canDownload}
                  downloadingId={download.isPending ? download.variables ?? null : null}
                  onDownload={handleDownload}
                  onDelete={setDeleteTarget}
                />
              )}
            </CardContent>
            {total > 0 ? (
              <CardFooter>
                <StoragePagination
                  page={page}
                  pageSize={STORAGE_PAGE_SIZE}
                  total={total}
                  q={q}
                />
              </CardFooter>
            ) : null}
          </Card>
        </>
      ) : null}

      {canDelete ? (
        <DeleteStorageFileDialog
          item={deleteTarget}
          open={Boolean(deleteTarget)}
          onOpenChange={(open) => {
            if (!open) setDeleteTarget(null);
          }}
          onConfirm={handleDelete}
          isPending={remove.isPending}
        />
      ) : null}
    </div>
  );
}
