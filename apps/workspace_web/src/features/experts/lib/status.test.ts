import { describe, expect, it } from 'vitest';
import { ingestionProgressDetail } from './status';

describe('ingestionProgressDetail', () => {
  it('shows waiting on the next page during OCR', () => {
    expect(
      ingestionProgressDetail({
        isPdf: true,
        pageCount: 10,
        processed: 9,
        currentStage: 'ocr',
      }),
    ).toEqual({ kind: 'waitingPage', page: 10, total: 10 });
  });

  it('starts waiting on page 1 when nothing is done yet', () => {
    expect(
      ingestionProgressDetail({
        isPdf: true,
        pageCount: 10,
        processed: 0,
        currentStage: 'ocr',
      }),
    ).toEqual({ kind: 'waitingPage', page: 1, total: 10 });
  });

  it('caps waiting page at total', () => {
    expect(
      ingestionProgressDetail({
        isPdf: true,
        pageCount: 3,
        processed: 3,
        currentStage: 'ocr',
      }),
    ).toEqual({ kind: 'pagesDone', processed: 3, total: 3 });
  });

  it('uses pages-done copy after OCR for later stages', () => {
    expect(
      ingestionProgressDetail({
        isPdf: true,
        pageCount: 10,
        processed: 10,
        currentStage: 'chunking',
      }),
    ).toEqual({ kind: 'pagesDone', processed: 10, total: 10 });
  });

  it('falls back to working for non-PDF', () => {
    expect(
      ingestionProgressDetail({
        isPdf: false,
        pageCount: 1,
        processed: 0,
        currentStage: 'parsing',
      }),
    ).toEqual({ kind: 'working' });
  });
});
