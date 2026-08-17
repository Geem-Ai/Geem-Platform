import { FileText, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export type ComposerAttachment = {
  /** Local UI id (stable while uploading). */
  id: string;
  /** Server id after successful upload; null while uploading. */
  serverId: string | null;
  name: string;
  mimeType?: string;
  byteSize?: number;
  /** Extension / type label, e.g. PDF */
  typeLabel: string;
  /** 0–100 upload progress */
  progress: number;
};

interface ComposerAttachmentPreviewProps {
  attachment: ComposerAttachment;
  onRemove: () => void;
  className?: string;
}

function CircularProgress({ value }: { value: number }) {
  const size = 28;
  const stroke = 2.5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, value));
  const offset = circumference - (clamped / 100) * circumference;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="shrink-0 -rotate-90"
      aria-hidden
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={stroke}
        className="text-muted-foreground/25"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        className="text-foreground transition-[stroke-dashoffset] duration-150 ease-out"
      />
    </svg>
  );
}

export function ComposerAttachmentPreview({
  attachment,
  onRemove,
  className,
}: ComposerAttachmentPreviewProps) {
  const { t } = useTranslation();
  const isUploading = attachment.progress < 100;

  return (
    <div
      data-testid="chat-attachment-preview"
      data-uploading={isUploading ? 'true' : 'false'}
      className={cn(
        'group relative inline-flex max-w-[16rem] items-center gap-2.5 rounded-2xl border bg-muted/40 px-2.5 py-2',
        className,
      )}
    >
      {isUploading ? (
        <CircularProgress value={attachment.progress} />
      ) : (
        <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <FileText className="size-3.5" />
        </span>
      )}

      <div className="min-w-0 flex-1 pe-5">
        <p className="truncate text-sm font-medium leading-tight text-foreground">
          {attachment.name}
        </p>
        <p className="mt-0.5 text-xs leading-tight text-muted-foreground uppercase tracking-wide">
          {attachment.typeLabel}
        </p>
      </div>

      <button
        type="button"
        data-testid="chat-attachment-remove"
        aria-label={t('chat.removeAttachment')}
        onClick={onRemove}
        className={cn(
          'absolute end-1.5 top-1.5 inline-flex size-5 items-center justify-center rounded-full',
          'bg-background/90 text-muted-foreground shadow-sm border',
          'hover:text-foreground transition-colors',
        )}
      >
        <X className="size-3" strokeWidth={2.5} />
      </button>
    </div>
  );
}

export function attachmentTypeLabel(fileName: string): string {
  const ext = fileName.includes('.')
    ? fileName.slice(fileName.lastIndexOf('.') + 1)
    : '';
  return (ext || 'FILE').toUpperCase();
}
