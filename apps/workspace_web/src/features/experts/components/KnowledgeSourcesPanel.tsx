import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ExpertKnowledgeItem } from '@/services/api/types';
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { useUnlinkExpertDocument, useReprocessDocument } from '../hooks/useExpertMutations';
import { docStatusBadgeVariant, docStatusLabelKey } from '../lib/status';
import { RemoveKnowledgeDialog } from './RemoveKnowledgeDialog';
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
  const [removeItem, setRemoveItem] = useState<ExpertKnowledgeItem | null>(null);

  const unlinkMutation = useUnlinkExpertDocument(expertId);
  const reprocessMutation = useReprocessDocument(expertId);

  function handleRemove(item: ExpertKnowledgeItem) {
    unlinkMutation.mutate(item.document_id, {
      onSuccess: () => {
        toast.success(t('experts.remove'));
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
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t('experts.knowledge')}</h3>
        {canManage && (
          <Button size="sm" onClick={() => setUploadOpen(true)}>
            {t('experts.upload')}
          </Button>
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
          {items.map((item) => (
            <div
              key={item.id}
              className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">
                  {item.title || item.original_filename}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge
                    variant={docStatusBadgeVariant(item.status)}
                    appearance="light"
                    size="sm"
                  >
                    {t(docStatusLabelKey(item.status))}
                  </Badge>
                  {item.page_count && item.page_count > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {item.page_count}p
                    </span>
                  )}
                  {item.failure_reason && (
                    <span className="text-xs text-destructive truncate max-w-[200px]">
                      {item.failure_reason}
                    </span>
                  )}
                </div>
              </div>
              {canManage && (
                <div className="flex items-center gap-2 shrink-0">
                  {item.status === 'failed' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleReprocess(item.document_id)}
                      disabled={reprocessMutation.isPending}
                    >
                      {t('experts.reprocess')}
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRemoveItem(item)}
                    disabled={unlinkMutation.isPending}
                  >
                    {t('experts.remove')}
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {canManage && (
        <>
          <UploadKnowledgeDialog
            expertId={expertId}
            open={uploadOpen}
            onOpenChange={setUploadOpen}
          />
          <RemoveKnowledgeDialog
            item={removeItem}
            open={Boolean(removeItem)}
            onOpenChange={(o) => { if (!o) setRemoveItem(null); }}
            onConfirm={handleRemove}
            isPending={unlinkMutation.isPending}
          />
        </>
      )}
    </div>
  );
}
