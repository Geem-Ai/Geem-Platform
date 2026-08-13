import { describe, expect, it } from 'vitest';
import {
  storageFileGlyphClass,
  storageFileKind,
  storageFileKindLabelKey,
} from './file-type';

describe('storageFileKind', () => {
  it('detects PDF from mime or extension', () => {
    expect(storageFileKind('application/pdf', 'a.bin')).toBe('pdf');
    expect(storageFileKind(null, 'deck.PDF')).toBe('pdf');
  });

  it('detects text and markdown', () => {
    expect(storageFileKind('text/plain', 'notes.txt')).toBe('text');
    expect(storageFileKind('text/markdown', 'readme.md')).toBe('markdown');
    expect(storageFileKind(null, 'guide.markdown')).toBe('markdown');
  });

  it('falls back to other', () => {
    expect(storageFileKind('application/octet-stream', 'blob')).toBe('other');
  });

  it('maps label keys and glyph tones', () => {
    expect(storageFileKindLabelKey('pdf')).toBe('storage.fileType.pdf');
    expect(storageFileGlyphClass('pdf')).toContain('destructive');
    expect(storageFileGlyphClass('text')).toContain('success');
  });
});
