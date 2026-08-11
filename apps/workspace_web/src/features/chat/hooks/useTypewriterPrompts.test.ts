import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTypewriterPrompts } from './useTypewriterPrompts';

function mockReducedMotion(reduced: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

async function tickChars(n: number) {
  for (let i = 0; i < n; i += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30);
    });
  }
}

describe('useTypewriterPrompts', () => {
  beforeEach(() => {
    mockReducedMotion(false);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('types the first prompt over time', async () => {
    const { result } = renderHook(() =>
      useTypewriterPrompts(['Hello', 'World'], false),
    );

    expect(result.current.visible[0]?.typed).toBe('');

    await tickChars(5);

    expect(result.current.visible[0]?.typed).toBe('Hello');
    expect(result.current.visible[0]?.done).toBe(true);
  });

  it('drops incomplete chips when paused (P2)', async () => {
    const { result, rerender } = renderHook(
      ({ paused }: { paused: boolean }) =>
        useTypewriterPrompts(['Hello', 'World'], paused),
      { initialProps: { paused: false } },
    );

    await tickChars(2); // "He"
    expect(result.current.visible[0]?.typed).toBe('He');
    expect(result.current.visible[0]?.done).toBe(false);

    rerender({ paused: true });

    expect(result.current.visible[0]?.typed).toBe('');
    expect(result.current.visible[0]?.done).toBe(false);
    expect(result.current.visible.every((v) => v.typed === '')).toBe(true);
  });

  it('keeps finished chips after language remap while paused (P3)', async () => {
    const { result, rerender } = renderHook(
      ({
        prompts,
        paused,
      }: {
        prompts: string[];
        paused: boolean;
      }) => useTypewriterPrompts(prompts, paused),
      {
        initialProps: {
          prompts: ['Hello', 'World'],
          paused: false,
        },
      },
    );

    await tickChars(5);
    expect(result.current.visible[0]?.done).toBe(true);

    rerender({ prompts: ['Hello', 'World'], paused: true });
    expect(result.current.visible[0]?.done).toBe(true);
    expect(result.current.visible[0]?.typed).toBe('Hello');

    // Language change → new strings, same finished count.
    rerender({ prompts: ['مرحبا', 'عالم'], paused: true });
    expect(result.current.visible[0]?.typed).toBe('مرحبا');
    expect(result.current.visible[0]?.done).toBe(true);
    expect(result.current.visible[1]?.typed).toBe('');
  });
});
