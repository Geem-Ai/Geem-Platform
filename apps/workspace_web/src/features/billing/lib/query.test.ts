import { describe, expect, it } from 'vitest';
import { keepPreviousIfSameWorkspace } from './query';

describe('keepPreviousIfSameWorkspace', () => {
  const previous = { items: [{ id: 'pur-a' }] };

  it('keeps previous data for the same workspace', () => {
    expect(
      keepPreviousIfSameWorkspace('ws-a', previous, {
        queryKey: ['workspace', 'ws-a', 'billing', 'purchases'],
      }),
    ).toBe(previous);
  });

  it('drops previous data when the workspace changes', () => {
    expect(
      keepPreviousIfSameWorkspace('ws-b', previous, {
        queryKey: ['workspace', 'ws-a', 'billing', 'purchases'],
      }),
    ).toBeUndefined();
  });
});
