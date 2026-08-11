import { useEffect, useRef, useState } from 'react';

const CHAR_MS = 28;
const HOLD_MS = 1600;
const DELETE_MS = 16;
const BETWEEN_MS = 280;

type Phase = 'typing' | 'holding' | 'deleting' | 'gap';

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Cycles through status strings with typewriter in / hold / delete out.
 * When `active` is false, timers stop and text clears.
 * Reduced motion → rotate full strings on a hold interval (no char animation).
 */
export function useTypewriterStatus(
  messages: string[],
  active: boolean,
): { text: string; messageIndex: number } {
  const messagesKey = messages.join('\0');
  const [index, setIndex] = useState(0);
  const [charLen, setCharLen] = useState(0);
  const [phase, setPhase] = useState<Phase>('typing');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setIndex(0);
    setCharLen(0);
    setPhase('typing');
  }, [messagesKey]);

  useEffect(() => {
    if (!active) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setIndex(0);
      setCharLen(0);
      setPhase('typing');
      return;
    }

    const list = messagesRef.current;
    if (list.length === 0) return;

    const current = list[index % list.length] ?? '';

    if (prefersReducedMotion()) {
      setCharLen(current.length);
      timerRef.current = setTimeout(() => {
        setIndex((i) => (i + 1) % list.length);
      }, HOLD_MS);
      return () => {
        if (timerRef.current) clearTimeout(timerRef.current);
      };
    }

    if (phase === 'typing') {
      if (charLen >= current.length) {
        setPhase('holding');
        return;
      }
      timerRef.current = setTimeout(() => {
        setCharLen((n) => Math.min(current.length, n + 1));
      }, CHAR_MS);
    } else if (phase === 'holding') {
      timerRef.current = setTimeout(() => {
        setPhase(list.length <= 1 ? 'holding' : 'deleting');
      }, HOLD_MS);
    } else if (phase === 'deleting') {
      if (charLen <= 0) {
        setPhase('gap');
        return;
      }
      timerRef.current = setTimeout(() => {
        setCharLen((n) => Math.max(0, n - 1));
      }, DELETE_MS);
    } else {
      timerRef.current = setTimeout(() => {
        setIndex((i) => (i + 1) % list.length);
        setCharLen(0);
        setPhase('typing');
      }, BETWEEN_MS);
    }

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [active, index, charLen, phase, messagesKey]);

  const list = messagesRef.current;
  if (!active || list.length === 0) {
    return { text: '', messageIndex: 0 };
  }
  const full = list[index % list.length] ?? '';
  return { text: full.slice(0, charLen), messageIndex: index % list.length };
}
