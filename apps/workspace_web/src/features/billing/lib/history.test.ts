import { describe, expect, it } from 'vitest';
import { statusQueryValue } from './history';

describe('statusQueryValue', () => {
  it('sends pending so the backend can include redirected checkouts', () => {
    expect(statusQueryValue('all')).toBeUndefined();
    expect(statusQueryValue('pending')).toBe('pending');
    expect(statusQueryValue('paid')).toBe('paid');
  });
});
