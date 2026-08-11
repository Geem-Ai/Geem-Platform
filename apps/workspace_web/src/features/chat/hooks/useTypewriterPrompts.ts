import { useEffect, useRef, useState } from 'react';

export interface TypewriterPromptItem {
  full: string;
  typed: string;
  done: boolean;
}

const CHAR_MS = 30;
const BETWEEN_CHIP_MS = 400;

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Sequentially typewriter-reveals an array of prompt strings.
 * When `paused`, timers stop and incomplete chips are dropped (only finished remain).
 * Reduced motion → all prompts appear fully typed immediately.
 * Prompt-set / language changes preserve already-finished chips when paused.
 */
export function useTypewriterPrompts(
  prompts: string[],
  paused: boolean,
): { visible: TypewriterPromptItem[]; allDone: boolean } {
  const promptsKey = prompts.join('\0');
  const [typedLengths, setTypedLengths] = useState<number[]>(() =>
    prefersReducedMotion() ? prompts.map((p) => p.length) : prompts.map(() => 0),
  );
  const [activeIndex, setActiveIndex] = useState(() =>
    prefersReducedMotion() ? prompts.length : 0,
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const promptsRef = useRef(prompts);
  promptsRef.current = prompts;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const doneCountRef = useRef(0);

  // Track how many chips finished (for language remount / pause preserve).
  useEffect(() => {
    const list = promptsRef.current;
    doneCountRef.current = list.reduce((count, full, i) => {
      const len = typedLengths[i] ?? 0;
      return len >= full.length && full.length > 0 ? count + 1 : count;
    }, 0);
  }, [typedLengths, promptsKey]);

  // Reset / remap when the prompt set changes (new selection or language).
  useEffect(() => {
    const list = promptsRef.current;
    if (prefersReducedMotion()) {
      setTypedLengths(list.map((p) => p.length));
      setActiveIndex(list.length);
      return;
    }
    if (pausedRef.current) {
      // Keep finished chips in the new language; drop incomplete ones.
      const keep = doneCountRef.current;
      setTypedLengths(list.map((p, i) => (i < keep ? p.length : 0)));
      setActiveIndex(list.length);
      return;
    }
    setTypedLengths(list.map(() => 0));
    setActiveIndex(0);
  }, [promptsKey]);

  // On pause: drop incomplete chips; keep finished ones clickable.
  useEffect(() => {
    if (!paused) return;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const list = promptsRef.current;
    setTypedLengths((prev) =>
      list.map((p, i) => {
        const len = prev[i] ?? 0;
        return len >= p.length ? p.length : 0;
      }),
    );
    setActiveIndex(list.length);
  }, [paused]);

  useEffect(() => {
    if (paused || prefersReducedMotion()) return;
    const list = promptsRef.current;
    if (activeIndex >= list.length) return;

    const current = list[activeIndex] ?? '';
    const typed = typedLengths[activeIndex] ?? 0;

    if (typed >= current.length) {
      timerRef.current = setTimeout(() => {
        setActiveIndex((i) => i + 1);
      }, BETWEEN_CHIP_MS);
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    }

    timerRef.current = setTimeout(() => {
      setTypedLengths((prev) => {
        const next = [...prev];
        next[activeIndex] = Math.min(current.length, (next[activeIndex] ?? 0) + 1);
        return next;
      });
    }, CHAR_MS);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [activeIndex, typedLengths, promptsKey, paused]);

  const list = promptsRef.current;
  const visible: TypewriterPromptItem[] = list.map((full, i) => {
    const len = typedLengths[i] ?? 0;
    return {
      full,
      typed: full.slice(0, len),
      done: full.length > 0 && len >= full.length,
    };
  });

  const allDone =
    list.length === 0 ||
    (activeIndex >= list.length && visible.every((item) => item.done));

  return { visible, allDone };
}
