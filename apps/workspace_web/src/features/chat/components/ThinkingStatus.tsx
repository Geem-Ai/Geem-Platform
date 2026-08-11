import { useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useTypewriterStatus } from '../hooks/useTypewriterStatus';
import { shuffleThinkingStatusKeys } from '../lib/thinkingStatuses';

interface ThinkingStatusProps {
  className?: string;
}

export function ThinkingStatus({ className }: ThinkingStatusProps) {
  const { t, i18n } = useTranslation();
  // Shuffle once per mount so the mix varies without reshuffling mid-stream.
  const keysRef = useRef<string[] | null>(null);
  if (keysRef.current === null) {
    keysRef.current = shuffleThinkingStatusKeys();
  }

  const messages = useMemo(
    () => (keysRef.current ?? []).map((key) => t(key)),
    [t, i18n.language],
  );

  const { text } = useTypewriterStatus(messages, true);

  return (
    <span
      className={cn('text-muted-foreground', className)}
      data-testid="thinking-status"
      aria-hidden
    >
      {text}
      <span
        className="inline-block w-px h-3.5 ms-0.5 align-middle bg-current animate-pulse"
        aria-hidden
      />
    </span>
  );
}
