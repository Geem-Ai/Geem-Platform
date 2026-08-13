import { describe, expect, it } from 'vitest';
import { tokenSharePercent } from './share';

describe('tokenSharePercent', () => {
  it('returns 0 when the total is empty or invalid', () => {
    expect(tokenSharePercent(10, 0)).toBe(0);
    expect(tokenSharePercent(10, -1)).toBe(0);
    expect(tokenSharePercent(10, Number.NaN)).toBe(0);
  });

  it('clamps a share of the billed total', () => {
    expect(tokenSharePercent(25, 100)).toBe(25);
    expect(tokenSharePercent(150, 100)).toBe(100);
    expect(tokenSharePercent(-8, 100)).toBe(0);
  });
});
