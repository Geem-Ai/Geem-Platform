import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useTypewriterStatus } from './useTypewriterStatus';

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

async function tickChars(n: number, ms = 28) {
  for (let i = 0; i < n; i += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }
}

describe('useTypewriterStatus', () => {
  beforeEach(() => {
    mockReducedMotion(false);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('types the first status message over time', async () => {
    const { result } = renderHook(() =>
      useTypewriterStatus(['Geem is thinking…', 'Checking sources…'], true),
    );

    expect(result.current.text).toBe('');

    await tickChars(5);
    expect(result.current.text).toBe('Geem ');
  });

  it('cycles to the next message after hold + delete', async () => {
    const { result } = renderHook(() =>
      useTypewriterStatus(['Hi', 'Yo'], true),
    );

    await tickChars(2);
    expect(result.current.text).toBe('Hi');

    // hold
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    // delete both chars
    await tickChars(2, 16);
    expect(result.current.text).toBe('');

    // gap then type next
    await act(async () => {
      await vi.advanceTimersByTimeAsync(280);
    });
    await tickChars(2);
    expect(result.current.text).toBe('Yo');
  });

  it('clears when inactive', async () => {
    const { result, rerender } = renderHook(
      ({ active }: { active: boolean }) =>
        useTypewriterStatus(['Thinking…'], active),
      { initialProps: { active: true } },
    );

    await tickChars(5);
    expect(result.current.text.length).toBeGreaterThan(0);

    rerender({ active: false });
    expect(result.current.text).toBe('');
  });

  it('shows full strings when reduced motion is preferred', async () => {
    mockReducedMotion(true);
    const { result } = renderHook(() =>
      useTypewriterStatus(['Alpha', 'Beta'], true),
    );

    expect(result.current.text).toBe('Alpha');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(result.current.text).toBe('Beta');
  });
});
