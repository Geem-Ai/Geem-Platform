/** UX-only file validation — server always re-validates. */

const ACCEPTED_EXTENSIONS = ['.pdf', '.txt', '.md'];
const ACCEPTED_MIME_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'text/x-markdown',
];
const MAX_BYTES = 50 * 1024 * 1024; // 50 MB

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

  if (file.size > MAX_BYTES) {
    return { valid: false, errorKey: 'errors.uploadTooLarge' };
  }

  return { valid: true };
}

export function acceptedFileTypes(): string {
  return ACCEPTED_EXTENSIONS.join(',');
}
