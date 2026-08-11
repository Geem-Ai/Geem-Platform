import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
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
import { ApiError, errorMessageKey } from '@/services/api/errors';
import { acceptedFileTypes, validateExpertFile } from '../lib/file-validation';
import { useUploadExpertDocument } from '../hooks/useExpertMutations';

interface UploadKnowledgeDialogProps {
  expertId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UploadKnowledgeDialog({
  expertId,
  open,
  onOpenChange,
}: UploadKnowledgeDialogProps) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const mutation = useUploadExpertDocument(expertId);

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
          if (data.reused) {
            toast.success(t('experts.reused'));
          } else {
            toast.success(t('experts.upload'));
          }
          setFile(null);
          setTitle('');
          onOpenChange(false);
        },
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

  function handleClose() {
    if (mutation.isPending) return;
    setFile(null);
    setTitle('');
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('experts.uploadTitle')}</DialogTitle>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <div
            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${dragging ? 'border-ring bg-accent/30' : 'border-border hover:border-muted-foreground/40'}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
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
              <div>
                <p className="text-sm text-muted-foreground">{t('experts.uploadHint')}</p>
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
            <Button type="button" variant="outline" onClick={handleClose} disabled={mutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!file || mutation.isPending}>
              {mutation.isPending ? t('experts.uploading') : t('experts.upload')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
