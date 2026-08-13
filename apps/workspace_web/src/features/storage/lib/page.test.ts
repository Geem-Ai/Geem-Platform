import { describe, expect, it } from 'vitest';
import { parseStoragePage, storagePageHref } from './page';

describe('storage page helpers', () => {
  it('parses page numbers', () => {
    expect(parseStoragePage(null)).toBe(1);
    expect(parseStoragePage('0')).toBe(1);
    expect(parseStoragePage('2.9')).toBe(2);
    expect(parseStoragePage('3')).toBe(3);
  });

  it('builds hrefs with page and q', () => {
    expect(storagePageHref(1)).toBe('/storage');
    expect(storagePageHref(2)).toBe('/storage?page=2');
    expect(storagePageHref(1, ' contract ')).toBe('/storage?q=contract');
    expect(storagePageHref(3, 'legal')).toBe('/storage?page=3&q=legal');
  });
});
