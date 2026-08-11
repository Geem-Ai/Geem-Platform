import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Stick-to-bottom while the user is near the end; pause when they scroll up.
 * Avoids scrollIntoView on every token.
 */
export function useStickToBottom(deps: unknown[] = []) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(true);
  const [showJump, setShowJump] = useState(false);

  const isNearBottom = useCallback((el: HTMLDivElement, threshold = 120) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
    setStuck(true);
    setShowJump(false);
  }, []);

  const onScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const near = isNearBottom(el);
    setStuck(near);
    setShowJump(!near);
  }, [isNearBottom]);

  useEffect(() => {
    if (!stuck) return;
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return {
    containerRef,
    bottomRef,
    stuck,
    showJump,
    onScroll,
    scrollToBottom,
  };
}
