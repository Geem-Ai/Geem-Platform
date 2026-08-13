import type { LucideIcon } from 'lucide-react';
import { FileCode2, FileText } from 'lucide-react';

export type StorageFileKind = 'pdf' | 'text' | 'markdown' | 'other';

export function storageFileKind(
  mimeType: string | null | undefined,
  filename: string | null | undefined,
): StorageFileKind {
  const mime = (mimeType ?? '').toLowerCase();
  const name = (filename ?? '').toLowerCase();
  if (mime.includes('pdf') || name.endsWith('.pdf')) return 'pdf';
  if (
    mime.includes('markdown') ||
    name.endsWith('.md') ||
    name.endsWith('.markdown')
  ) {
    return 'markdown';
  }
  if (
    mime.startsWith('text/') ||
    name.endsWith('.txt') ||
    name.endsWith('.text')
  ) {
    return 'text';
  }
  return 'other';
}

export function storageFileKindLabelKey(kind: StorageFileKind): string {
  if (kind === 'pdf') return 'storage.fileType.pdf';
  if (kind === 'text') return 'storage.fileType.text';
  if (kind === 'markdown') return 'storage.fileType.markdown';
  return 'storage.fileType.other';
}

export function storageFileIcon(kind: StorageFileKind): LucideIcon {
  if (kind === 'markdown') return FileCode2;
  return FileText;
}

export function storageFileGlyphClass(kind: StorageFileKind): string {
  if (kind === 'pdf') {
    return 'bg-[var(--color-destructive-soft,rgba(239,68,68,0.12))] text-[var(--color-destructive,var(--color-red-700))]';
  }
  if (kind === 'markdown') {
    return 'bg-primary/10 text-primary';
  }
  if (kind === 'text') {
    return 'bg-[var(--color-success-soft,var(--color-green-100))] text-[var(--color-success-accent,var(--color-green-700))]';
  }
  return 'bg-muted text-muted-foreground';
}
