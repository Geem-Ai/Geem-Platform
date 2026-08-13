import { cn } from '@/lib/utils';
import {
  storageFileGlyphClass,
  storageFileIcon,
  type StorageFileKind,
} from '../lib/file-type';

type StorageFileGlyphProps = {
  kind: StorageFileKind;
  label: string;
  className?: string;
};

/** Distinct file-type tile — PDF shows a PDF mark instead of a generic “T” icon. */
export function StorageFileGlyph({ kind, label, className }: StorageFileGlyphProps) {
  const Icon = storageFileIcon(kind);
  return (
    <div
      className={cn(
        'size-11 rounded-xl flex flex-col items-center justify-center shrink-0 border border-border/60',
        storageFileGlyphClass(kind),
        className,
      )}
      aria-hidden
      title={label}
    >
      {kind === 'pdf' ? (
        <span className="text-[10px] font-bold tracking-wide leading-none">PDF</span>
      ) : (
        <>
          <Icon className="size-4" />
          <span className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide leading-none opacity-80">
            {kind === 'markdown' ? 'MD' : kind === 'text' ? 'TXT' : 'FILE'}
          </span>
        </>
      )}
    </div>
  );
}
