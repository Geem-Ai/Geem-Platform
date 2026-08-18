import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, Sparkles, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  docStatusBadgeVariant,
  docStatusLabelKey,
} from '@/features/experts/lib/status';
import {
  formatBytesLabel,
  formatRelativeTime,
  type ByteUnitKey,
} from '@/features/usage/lib/quota';
import { cn } from '@/lib/utils';
import type { DocumentSummary } from '@/services/api/types';
import {
  storageFileKind,
  storageFileKindLabelKey,
} from '../lib/file-type';
import { StorageFileGlyph } from './StorageFileGlyph';

type StorageFileListProps = {
  items: DocumentSummary[];
  canDelete: boolean;
  canDownload: boolean;
  downloadingId: string | null;
  onDownload: (item: DocumentSummary) => void;
  onDelete: (item: DocumentSummary) => void;
};

function pageCountLabel(
  count: number,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  return count === 1
    ? t('storage.pageCountOne', { count })
    : t('storage.pageCountOther', { count });
}

export function StorageFileList({
  items,
  canDelete,
  canDownload,
  downloadingId,
  onDownload,
  onDelete,
}: StorageFileListProps) {
  const { t, i18n } = useTranslation();
  const byteUnit = (unit: ByteUnitKey) => t(`usage.units.${unit}`);

  return (
    <div data-testid="storage-file-list">
      <div
        className={cn(
          'hidden sm:grid items-center gap-4 px-5 h-9 border-b border-border',
          'bg-muted/40 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground',
          canDelete || canDownload
            ? 'grid-cols-[minmax(0,1fr)_6.5rem_11rem]'
            : 'grid-cols-[minmax(0,1fr)_6.5rem_7.5rem]',
        )}
        role="row"
      >
        <span role="columnheader">{t('storage.columnFile')}</span>
        <span role="columnheader" className="text-end">
          {t('storage.columnSize')}
        </span>
        <span role="columnheader" className="text-end">
          {t('storage.columnActions')}
        </span>
      </div>

      <div className="divide-y divide-border">
        {items.map((item) => {
          const experts = item.experts ?? [];
          const orphan = experts.length === 0;
          const kind = storageFileKind(item.mime_type, item.original_filename);
          const kindLabel = t(storageFileKindLabelKey(kind));
          const title = item.title || item.original_filename;
          const downloading = downloadingId === item.id;
          const showFilename =
            Boolean(item.title) &&
            item.title.trim().toLowerCase() !==
              item.original_filename.trim().toLowerCase();
          const createdLabel = item.created_at
            ? formatRelativeTime(item.created_at, i18n.language)
            : null;
          const sizeLabel = formatBytesLabel(
            item.byte_size ?? 0,
            i18n.language,
            byteUnit,
          );

          return (
            <div
              key={item.id}
              className={cn(
                'group px-4 py-4 sm:px-5 transition-colors hover:bg-muted/35',
                'flex flex-col gap-3 sm:grid sm:items-center sm:gap-4',
                canDelete || canDownload
                  ? 'sm:grid-cols-[minmax(0,1fr)_6.5rem_11rem]'
                  : 'sm:grid-cols-[minmax(0,1fr)_6.5rem_7.5rem]',
              )}
              data-testid={`storage-row-${item.id}`}
            >
              <div className="min-w-0 flex items-start gap-3">
                <StorageFileGlyph kind={kind} label={kindLabel} />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-semibold truncate leading-5">{title}</p>
                    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground/75">{kindLabel}</span>
                      {showFilename ? (
                        <>
                          <span aria-hidden>·</span>
                          <span
                            className="truncate max-w-[18rem]"
                            title={item.original_filename}
                            dir="auto"
                          >
                            {item.original_filename}
                          </span>
                        </>
                      ) : null}
                      {item.page_count != null && item.page_count > 0 ? (
                        <>
                          <span aria-hidden>·</span>
                          <span className="tabular-nums">
                            {pageCountLabel(item.page_count, t)}
                          </span>
                        </>
                      ) : null}
                      {createdLabel ? (
                        <>
                          <span aria-hidden>·</span>
                          <span title={item.created_at ?? undefined}>{createdLabel}</span>
                        </>
                      ) : null}
                      <span className="sm:hidden" aria-hidden>
                        ·
                      </span>
                      <span className="sm:hidden tabular-nums font-medium text-foreground/80">
                        {sizeLabel}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge
                      variant={docStatusBadgeVariant(item.status)}
                      appearance="light"
                      size="sm"
                    >
                      {t(docStatusLabelKey(item.status))}
                    </Badge>
                    {orphan ? (
                      <Badge
                        variant="warning"
                        appearance="light"
                        size="sm"
                        data-testid={`storage-orphan-${item.id}`}
                      >
                        {t('storage.orphan')}
                      </Badge>
                    ) : (
                      experts.map((expert) => (
                        <Button
                          key={expert.id}
                          variant="outline"
                          size="sm"
                          className="h-6 max-w-[12rem] px-2 text-xs"
                          asChild
                        >
                          <Link
                            to={`/experts/${expert.id}`}
                            className="inline-flex min-w-0 items-center gap-1"
                          >
                            <Sparkles
                              className="size-3 shrink-0 text-muted-foreground"
                              aria-hidden
                            />
                            <span className="truncate">{expert.name}</span>
                          </Link>
                        </Button>
                      ))
                    )}
                  </div>
                </div>
              </div>

              <p className="hidden sm:block text-sm font-semibold tabular-nums text-end tracking-tight">
                {sizeLabel}
              </p>

              <div className="flex items-center justify-stretch sm:justify-end gap-2 shrink-0">
                {canDownload ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onDownload(item)}
                        disabled={downloading}
                        data-testid={`storage-download-${item.id}`}
                        aria-label={t('common.download')}
                        className="flex-1 sm:flex-none"
                      >
                        {downloading ? (
                          <Loader2 className="size-3.5 animate-spin" aria-hidden />
                        ) : (
                          <Download className="size-3.5" aria-hidden />
                        )}
                        <span>
                          {downloading ? t('storage.downloading') : t('common.download')}
                        </span>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">{t('storage.downloadHint')}</TooltipContent>
                  </Tooltip>
                ) : null}
                {canDelete ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        mode="icon"
                        className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                        onClick={() => onDelete(item)}
                        data-testid={`storage-delete-${item.id}`}
                        aria-label={t('common.delete')}
                      >
                        <Trash2 className="size-3.5" aria-hidden />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">{t('storage.deleteActionHint')}</TooltipContent>
                  </Tooltip>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
