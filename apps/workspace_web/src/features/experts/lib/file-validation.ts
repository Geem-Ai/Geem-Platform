/** UX-only file validation — server always re-validates. */

const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md'];
const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'text/x-markdown',
];

/**
 * Client-side UX guards. Server ``MAX_UPLOAD_MB`` / ``MAX_PDF_PAGES`` are authoritative.
 * Optional overrides: ``VITE_MAX_UPLOAD_MB``, ``VITE_MAX_PDF_PAGES``.
 */
const _maxMbRaw = Number(import.meta.env.VITE_MAX_UPLOAD_MB);
export const MAX_UPLOAD_MB =
  Number.isFinite(_maxMbRaw) && _maxMbRaw > 0 ? _maxMbRaw : 100;
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

const _maxPagesRaw = Number(import.meta.env.VITE_MAX_PDF_PAGES);
export const MAX_PDF_PAGES =
  Number.isFinite(_maxPagesRaw) && _maxPagesRaw > 0 ? _maxPagesRaw : 1000;

export type FileValidationResult =
  | { valid: true }
  | { valid: false; errorKey: string };

export function validateExpertFile(file: File): FileValidationResult {
  const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '');
  const mimeOk = ACCEPTED_MIME_TYPES.includes(file.type);
  const extOk = ACCEPTED_EXTENSIONS.includes(ext);

  if (!mimeOk && !extOk) {
    return { valid: false, errorKey: 'errors.uploadTypeRejected' };
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return { valid: false, errorKey: 'errors.uploadTooLarge' };
  }

  return { valid: true };
}

export function acceptedFileTypes(): string {
  return ACCEPTED_EXTENSIONS.join(',');
}
