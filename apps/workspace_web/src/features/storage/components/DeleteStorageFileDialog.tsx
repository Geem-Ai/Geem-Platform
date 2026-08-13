import { useTranslation } from 'react-i18next';
import { AlertTriangle, HardDrive, Link2Off, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatBytesLabel, type ByteUnitKey } from '@/features/usage/lib/quota';
import type { DocumentSummary } from '@/services/api/types';
import { storageFileIcon, storageFileKind } from '../lib/file-type';

type DeleteStorageFileDialogProps = {
  item: DocumentSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (item: DocumentSummary) => void;
  isPending?: boolean;
};

export function DeleteStorageFileDialog({
  item,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: DeleteStorageFileDialogProps) {
  const { t, i18n } = useTranslation();
  const byteUnit = (unit: ByteUnitKey) => t(`usage.units.${unit}`);

  if (!item) return null;

  const kind = storageFileKind(item.mime_type, item.original_filename);
  const FileIcon = storageFileIcon(kind);
  const title = item.title || item.original_filename;
  const effects = [
    { icon: Link2Off, text: t('storage.deleteEffectExperts') },
    { icon: HardDrive, text: t('storage.deleteEffectQuota') },
    { icon: Sparkles, text: t('storage.deleteEffectIndex') },
  ] as const;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!isPending) onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('storage.deleteTitle')}</DialogTitle>
          <DialogDescription>{t('storage.deleteHint')}</DialogDescription>
        </DialogHeader>

        <div className="rounded-xl border border-border bg-muted/30 p-3 flex items-start gap-3">
          <div className="size-10 rounded-lg bg-destructive/10 text-destructive flex items-center justify-center shrink-0">
            <FileIcon className="size-4" aria-hidden />
          </div>
          <div className="min-w-0 space-y-0.5">
            <p className="text-sm font-medium truncate">{title}</p>
            <p className="text-xs text-muted-foreground truncate">
              {item.original_filename}
              <span aria-hidden> · </span>
              {formatBytesLabel(item.byte_size ?? 0, i18n.language, byteUnit)}
            </p>
          </div>
        </div>

        <div
          role="note"
          className="rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-3 space-y-2"
        >
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="size-4 shrink-0" aria-hidden />
            <p className="text-sm font-medium">{t('storage.deleteIrreversible')}</p>
          </div>
          <ul className="space-y-2">
            {effects.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-2 text-xs text-muted-foreground">
                <Icon className="size-3.5 mt-0.5 shrink-0" aria-hidden />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => onConfirm(item)}
            disabled={isPending}
            data-testid="storage-delete-confirm"
          >
            {isPending ? t('storage.deleting') : t('storage.confirmDelete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
