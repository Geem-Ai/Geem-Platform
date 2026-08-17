import { describe, expect, it } from 'vitest';
import { validateExpertFile } from './file-validation';

function makeFile(name: string, type: string, size: number = 1000): File {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
}

describe('validateExpertFile', () => {
  it('accepts PDF by mime type', () => {
    const result = validateExpertFile(makeFile('doc.pdf', 'application/pdf'));
    expect(result.valid).toBe(true);
  });

  it('accepts TXT by mime type', () => {
    const result = validateExpertFile(makeFile('doc.txt', 'text/plain'));
    expect(result.valid).toBe(true);
  });

  it('accepts Markdown by extension when mime is missing', () => {
    const result = validateExpertFile(makeFile('doc.md', ''));
    expect(result.valid).toBe(true);
  });

  it('rejects unsupported types', () => {
    const result = validateExpertFile(makeFile('doc.docx', 'application/msword'));
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errorKey).toBe('errors.uploadTypeRejected');
    }
  });

  it('rejects files over the max upload size', () => {
    const overLimit = 101 * 1024 * 1024;
    const result = validateExpertFile(makeFile('large.pdf', 'application/pdf', overLimit));
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect(result.errorKey).toBe('errors.uploadTooLarge');
    }
  });
});
