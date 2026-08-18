import { useState } from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { ExpertKnowledgeItem } from '@/services/api/types';
import { ApiError, errorMessageKey, friendlyDisplayError } from '@/services/api/errors';
import { useUnlinkExpertDocument, useReprocessDocument } from '../hooks/useExpertMutations';
import { docStatusBadgeVariant, docStatusLabelKey, isProcessingDocStatus } from '../lib/status';
import { AddGoogleDriveKnowledgeDialog } from './AddGoogleDriveKnowledgeDialog';
import { AddOneDriveKnowledgeDialog } from './AddOneDriveKnowledgeDialog';
import { KnowledgeIngestionProgress } from './KnowledgeIngestionProgress';
import { RemoveKnowledgeDialog } from './RemoveKnowledgeDialog';
import { RenameKnowledgeDialog } from './RenameKnowledgeDialog';
import { UploadKnowledgeDialog } from './UploadKnowledgeDialog';

interface KnowledgeSourcesPanelProps {
  expertId: string;
  items: ExpertKnowledgeItem[];
  canManage: boolean;
  isLoading?: boolean;
  isError?: boolean;
}

export function KnowledgeSourcesPanel({
  expertId,
  items,
  canManage,
  isLoading,
  isError,
}: KnowledgeSourcesPanelProps) {
  const { t } = useTranslation();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [driveOpen, setDriveOpen] = useState(false);
  const [oneDriveOpen, setOneDriveOpen] = useState(false);
  const [removeItem, setRemoveItem] = useState<ExpertKnowledgeItem | null>(null);
  const [renameItem, setRenameItem] = useState<ExpertKnowledgeItem | null>(null);

  const unlinkMutation = useUnlinkExpertDocument(expertId);
  const reprocessMutation = useReprocessDocument(expertId);

  function handleRemove(item: ExpertKnowledgeItem) {
    unlinkMutation.mutate(item, {
      onSuccess: () => {
        toast.success(t('experts.removed'));
        setRemoveItem(null);
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

  function handleReprocess(documentId: string) {
    if (!window.confirm(t('experts.reprocessConfirm'))) return;
    reprocessMutation.mutate(
      { documentId, mode: 'full' },
      {
        onError: (err: unknown) => {
          if (err instanceof ApiError) {
            toast.error(t(errorMessageKey(err.code)));
          } else {
            toast.error(t('errors.generic'));
          }
        },
      },
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t('experts.knowledge')}</h3>
        {canManage && (
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDriveOpen(true)}
              data-testid="add-google-drive-knowledge"
            >
              <img
                src="/brand/apps/google-drive.svg"
                alt=""
                className="size-3.5"
                aria-hidden
              />
              {t('experts.googleDrive.add')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setOneDriveOpen(true)}
              data-testid="add-onedrive-knowledge"
            >
              <img
                src="/brand/apps/microsoft-onedrive.svg"
                alt=""
                className="size-3.5"
                aria-hidden
              />
              {t('experts.oneDrive.add')}
            </Button>
            <Button size="sm" onClick={() => setUploadOpen(true)}>
              {t('experts.upload')}
            </Button>
          </div>
        )}
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">{t('shell.loading')}</p>
      )}
      {isError && (
        <p className="text-sm text-destructive">{t('errors.generic')}</p>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="rounded-lg border border-border p-6 text-center">
          <p className="text-sm font-medium">{t('experts.knowledgeEmpty')}</p>
          {canManage && (
            <p className="text-xs text-muted-foreground mt-1">
              {t('experts.knowledgeEmptyHint')}
            </p>
          )}
        </div>
      )}

      {items.length > 0 && (
        <div className="divide-y divide-border rounded-lg border border-border">
          {items.map((item) => {
            const processing = isProcessingDocStatus(item.status);
            return (
              <div
                key={item.id}
                className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="min-w-0 flex-1 space-y-2">
                  <div>
                    <p className="text-sm font-medium truncate">
                      {item.title || item.original_filename}
                    </p>
                    <div className="flex flex-wrap items-center gap-2 mt-0.5">
                      <Badge
                        variant={docStatusBadgeVariant(item.status)}
                        appearance="light"
                        size="sm"
                      >
                        {t(docStatusLabelKey(item.status))}
                      </Badge>
                      {!processing && item.page_count != null && item.page_count > 0 && (
                        <span className="text-xs text-muted-foreground">
                          {t('experts.pageCount', { count: item.page_count })}
                        </span>
                      )}
                      {item.failure_reason && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-xs text-destructive truncate max-w-[240px] cursor-help">
                              {friendlyDisplayError(t, {
                                message: item.failure_reason,
                              })}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent
                            side="top"
                            className="max-w-sm whitespace-pre-wrap break-words"
                          >
                            {friendlyDisplayError(t, {
                              message: item.failure_reason,
                            })}
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                  <KnowledgeIngestionProgress item={item} />
                </div>
                {canManage && (
                  <div className="flex items-center gap-2 shrink-0">
                    {item.status === 'failed' && item.document_id && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleReprocess(item.document_id!)}
                        disabled={reprocessMutation.isPending}
                      >
                        {t('experts.reprocess')}
                      </Button>
                    )}
                    {item.document_id ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            mode="icon"
                            className="text-muted-foreground hover:text-foreground hover:bg-accent"
                            onClick={() => setRenameItem(item)}
                            aria-label={t('experts.rename')}
                            data-testid={`rename-knowledge-${item.id}`}
                          >
                            <Pencil className="size-3.5" aria-hidden />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">{t('experts.rename')}</TooltipContent>
                      </Tooltip>
                    ) : null}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          mode="icon"
                          className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                          onClick={() => setRemoveItem(item)}
                          disabled={
                            unlinkMutation.isPending ||
                            (processing && Boolean(item.document_id))
                          }
                          aria-label={t('experts.remove')}
                          data-testid={`remove-knowledge-${item.id}`}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top">{t('experts.remove')}</TooltipContent>
                    </Tooltip>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {canManage && (
        <>
          <UploadKnowledgeDialog
            expertId={expertId}
            open={uploadOpen}
            onOpenChange={setUploadOpen}
            knowledgeItems={items}
          />
          <AddGoogleDriveKnowledgeDialog
            expertId={expertId}
            open={driveOpen}
            onOpenChange={setDriveOpen}
          />
          <AddOneDriveKnowledgeDialog
            expertId={expertId}
            open={oneDriveOpen}
            onOpenChange={setOneDriveOpen}
          />
          <RemoveKnowledgeDialog
            item={removeItem}
            open={Boolean(removeItem)}
            onOpenChange={(o) => {
              if (!o) setRemoveItem(null);
            }}
            onConfirm={handleRemove}
            isPending={unlinkMutation.isPending}
          />
          <RenameKnowledgeDialog
            expertId={expertId}
            item={renameItem}
            open={Boolean(renameItem)}
            onOpenChange={(o) => {
              if (!o) setRenameItem(null);
            }}
          />
        </>
      )}
    </div>
  );
}
