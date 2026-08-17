import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, FileUp } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { ExpertKnowledgeItem } from '@/services/api/types';
import { ApiError, errorMessageKey, friendlyDisplayError } from '@/services/api/errors';
import { QuotaAlert } from '@/features/usage/components/QuotaAlert';
import { QuotaMeter } from '@/features/usage/components/QuotaMeter';
import { useUsageSummary } from '@/features/usage/hooks/useUsageQueries';
import { meterWarningLevel } from '@/features/usage/lib/quota';
import {
  acceptedFileTypes,
  MAX_PDF_PAGES,
  MAX_UPLOAD_MB,
  validateExpertFile,
} from '../lib/file-validation';
import { useUploadExpertDocument } from '../hooks/useExpertMutations';
import { isProcessingDocStatus } from '../lib/status';
import { KnowledgeIngestionProgress } from './KnowledgeIngestionProgress';

interface UploadKnowledgeDialogProps {
  expertId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Live knowledge list — used to show post-upload ingestion progress. */
  knowledgeItems?: ExpertKnowledgeItem[];
}

export function UploadKnowledgeDialog({
  expertId,
  open,
  onOpenChange,
  knowledgeItems = [],
}: UploadKnowledgeDialogProps) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [dragging, setDragging] = useState(false);
  const [trackingDocId, setTrackingDocId] = useState<string | null>(null);
  const [uploadDone, setUploadDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const mutation = useUploadExpertDocument(expertId);
  const usageQuery = useUsageSummary();
  const storage = usageQuery.data?.storage;
  const storageBytes = usageQuery.data?.storage_bytes;
  const storageExhausted =
    storage != null &&
    meterWarningLevel({
      limit: storage.limit_bytes,
      used: storage.used_bytes,
      reserved: storage.reserved_bytes,
      remaining: storage.remaining_bytes,
      period_start: storageBytes?.period_start ?? null,
      period_end: storageBytes?.period_end ?? null,
    }) === 'exhausted';
  const [storageQuotaCode, setStorageQuotaCode] = useState<
    'storage_quota_exceeded' | null
  >(null);

  const trackedItem = trackingDocId
    ? knowledgeItems.find((item) => item.document_id === trackingDocId)
    : undefined;

  const trackingComplete =
    Boolean(trackedItem) && !isProcessingDocStatus(trackedItem!.status);
  const toastedStatusRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setTitle('');
      setTrackingDocId(null);
      setUploadDone(false);
      setDragging(false);
      toastedStatusRef.current = null;
      setStorageQuotaCode(null);
    }
  }, [open]);

  useEffect(() => {
    if (!trackingDocId || !trackedItem) return;
    const status = trackedItem.status;
    if (status !== 'ready' && status !== 'failed') return;
    if (toastedStatusRef.current === status) return;
    toastedStatusRef.current = status;
    if (status === 'ready') {
      toast.success(t('experts.processingReady'));
    } else {
      toast.error(t('experts.processingFailed'));
    }
  }, [trackedItem, trackingDocId, t]);

  function pickFile(f: File) {
    const result = validateExpertFile(f);
    if (!result.valid) {
      toast.error(t(result.errorKey));
      return;
    }
    setFile(f);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) pickFile(dropped);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;

    mutation.mutate(
      { file, title: title.trim() || null },
      {
        onSuccess: (data) => {
          setUploadDone(true);
          setTrackingDocId(data.document_id);
          if (data.reused && data.status === 'ready') {
            toast.success(t('experts.reused'));
            setFile(null);
            setTitle('');
            onOpenChange(false);
            return;
          }
          if (data.reused) {
            toast.success(t('experts.reused'));
          } else {
            toast.success(t('experts.uploadStarted'));
          }
        },
        onError: (err: unknown) => {
          if (err instanceof ApiError) {
            if (err.code === 'storage_quota_exceeded') {
              setStorageQuotaCode('storage_quota_exceeded');
            }
            toast.error(t(errorMessageKey(err.code)));
          } else {
            toast.error(t('errors.generic'));
          }
        },
      },
    );
  }

  function handleClose() {
    if (mutation.isPending) return;
    setFile(null);
    setTitle('');
    setTrackingDocId(null);
    setUploadDone(false);
    onOpenChange(false);
  }

  const showProgress = Boolean(trackingDocId);

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) handleClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {showProgress ? t('experts.processingTitle') : t('experts.uploadTitle')}
          </DialogTitle>
        </DialogHeader>

        {showProgress ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-border p-4 space-y-3">
              <div className="flex items-start gap-3">
                {trackingComplete && trackedItem?.status === 'ready' ? (
                  <CheckCircle2 className="size-5 text-green-600 shrink-0 mt-0.5" aria-hidden />
                ) : (
                  <FileUp className="size-5 text-muted-foreground shrink-0 mt-0.5" aria-hidden />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {trackedItem?.title ||
                      trackedItem?.original_filename ||
                      file?.name ||
                      t('experts.upload')}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {trackingComplete
                      ? trackedItem?.status === 'ready'
                        ? t('experts.processingReady')
                        : t('experts.processingFailed')
                      : t('experts.processingHint')}
                  </p>
                </div>
              </div>

              {trackedItem ? (
                <KnowledgeIngestionProgress item={trackedItem} />
              ) : (
                <KnowledgeIngestionProgress
                  item={{
                    status: 'queued',
                    page_count: 0,
                    processed_pages: 0,
                    progress: 0,
                    current_stage: null,
                    mime_type: file?.type ?? null,
                  }}
                />
              )}

              {trackedItem?.failure_reason && (
                <p className="text-xs text-destructive">
                  {friendlyDisplayError(t, {
                    message: trackedItem.failure_reason,
                  })}
                </p>
              )}
            </div>

            <DialogFooter>
              <Button type="button" onClick={handleClose}>
                {trackingComplete ? t('shell.close') : t('experts.processingContinue')}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            {storage ? (
              <QuotaMeter
                title={t('quota.storageCurrent')}
                meter={{
                  limit: storage.limit_bytes,
                  used: storage.used_bytes,
                  reserved: storage.reserved_bytes,
                  remaining: storage.remaining_bytes,
                  period_start: storageBytes?.period_start ?? null,
                  period_end: storageBytes?.period_end ?? null,
                }}
                testId="upload-storage-meter"
                format="bytes"
                compact
              />
            ) : null}
            {storageExhausted || storageQuotaCode ? (
              <QuotaAlert code="storage_quota_exceeded" level="exhausted" />
            ) : null}
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${dragging ? 'border-ring bg-accent/30' : 'border-border hover:border-muted-foreground/40'}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
            >
              <input
                ref={inputRef}
                type="file"
                accept={acceptedFileTypes()}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) pickFile(f);
                }}
              />
              {file ? (
                <div>
                  <p className="text-sm font-medium truncate">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="text-sm text-muted-foreground">
                    {t('experts.uploadHint')}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t('experts.uploadLimits', {
                      maxMb: MAX_UPLOAD_MB,
                      maxPages: MAX_PDF_PAGES,
                    })}
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="upload-title">{t('experts.titleLabel')}</Label>
              <Input
                id="upload-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t('experts.titleOptional')}
                disabled={mutation.isPending}
              />
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={handleClose}
                disabled={mutation.isPending}
              >
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={!file || mutation.isPending || uploadDone}>
                {mutation.isPending ? t('experts.uploading') : t('experts.upload')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
