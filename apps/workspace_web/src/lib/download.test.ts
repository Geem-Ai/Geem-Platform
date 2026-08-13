import { describe, expect, it, vi } from 'vitest';
import { filenameFromContentDisposition } from '@/services/api/client';
import { triggerBrowserDownload } from './download';

describe('filenameFromContentDisposition', () => {
  it('prefers RFC 5987 filename*', () => {
    expect(
      filenameFromContentDisposition(
        "attachment; filename=\"doc.pdf\"; filename*=UTF-8''%D9%85%D9%84%D9%81.pdf",
      ),
    ).toBe('ملف.pdf');
  });

  it('falls back to quoted filename', () => {
    expect(filenameFromContentDisposition('attachment; filename="notes.txt"')).toBe(
      'notes.txt',
    );
  });
});

describe('triggerBrowserDownload', () => {
  it('creates an object URL and clicks an anchor', () => {
    const click = vi.fn();
    const createObjectURL = vi.fn(() => 'blob:test');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(click);
    triggerBrowserDownload(new Blob(['x']), 'a.txt');
    expect(createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');
    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });
});
