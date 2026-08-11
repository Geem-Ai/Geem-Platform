import type { VariantProps } from 'class-variance-authority';
import type { badgeVariants } from '@/components/ui/badge';

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>['variant']>;

/** i18n key for a given expert or document status string. */
export function expertStatusLabelKey(status: string): string {
  const map: Record<string, string> = {
    draft: 'experts.status.draft',
    processing: 'experts.status.processing',
    ready: 'experts.status.ready',
    failed: 'experts.status.failed',
    disabled: 'experts.status.disabled',
  };
  return map[status] ?? 'experts.status.draft';
}

export function docStatusLabelKey(status: string): string {
  const map: Record<string, string> = {
    queued: 'experts.docStatus.queued',
    pending: 'experts.docStatus.pending',
    processing: 'experts.docStatus.processing',
    ready: 'experts.docStatus.ready',
    failed: 'experts.docStatus.failed',
  };
  return map[status] ?? 'experts.docStatus.pending';
}

export function expertStatusBadgeVariant(status: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    ready: 'success',
    processing: 'warning',
    draft: 'secondary',
    failed: 'destructive',
    disabled: 'secondary',
  };
  return map[status] ?? 'secondary';
}

export function docStatusBadgeVariant(status: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    ready: 'success',
    processing: 'warning',
    queued: 'warning',
    pending: 'secondary',
    failed: 'destructive',
  };
  return map[status] ?? 'secondary';
}

export function isProcessingExpertStatus(status: string): boolean {
  return status === 'processing' || status === 'draft';
}

export function isProcessingDocStatus(status: string): boolean {
  return status === 'queued' || status === 'pending' || status === 'processing';
}

export function ingestionStageLabelKey(stage: string | null | undefined): string | null {
  if (!stage) return null;
  const map: Record<string, string> = {
    ocr: 'experts.stage.ocr',
    parsing: 'experts.stage.parsing',
    chunking: 'experts.stage.chunking',
    embedding: 'experts.stage.embedding',
    indexed: 'experts.stage.indexed',
    ready: 'experts.stage.ready',
  };
  return map[stage] ?? null;
}
