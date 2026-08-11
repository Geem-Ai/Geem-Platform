import { useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useTypewriterPrompts } from '../hooks/useTypewriterPrompts';
import { pickSamplePromptKeys } from '../lib/samplePrompts';

interface SamplePromptSuggestionsProps {
  paused: boolean;
  onSelect: (prompt: string) => void;
  className?: string;
}

export function SamplePromptSuggestions({
  paused,
  onSelect,
  className,
}: SamplePromptSuggestionsProps) {
  const { t, i18n } = useTranslation();
  // Pick once per mount (survives Strict Mode double-invoke via ref).
  const keysRef = useRef<string[] | null>(null);
  if (keysRef.current === null) {
    keysRef.current = pickSamplePromptKeys(5);
  }

  const prompts = useMemo(
    () => (keysRef.current ?? []).map((key) => t(key)),
    [t, i18n.language],
  );

  const { visible } = useTypewriterPrompts(prompts, paused);

  // While typing: show finished chips + the one in progress.
  // While paused: only finished chips (incomplete were cleared by the hook).
  const shown = paused
    ? visible.filter((item) => item.done)
    : visible.filter((item, i) => i === 0 || item.typed.length > 0 || visible[i - 1]?.done);

  return (
    <div
      className={cn('flex flex-wrap justify-center gap-2 mt-5', className)}
      data-testid="sample-prompts"
    >
      {shown.map((item, i) => (
        <Button
          key={`sample-${i}-${item.full.slice(0, 12)}`}
          type="button"
          variant="outline"
          size="sm"
          disabled={!item.done}
          onClick={() => {
            if (!item.done) return;
            onSelect(item.full);
          }}
          className={cn(
            'h-auto max-w-full whitespace-normal text-start text-xs font-normal rounded-full px-3.5 py-2',
            'border-border/80 bg-background hover:bg-muted text-muted-foreground hover:text-foreground',
            !item.done && 'opacity-80 cursor-default',
          )}
          data-testid={`sample-prompt-${i}`}
          data-done={item.done ? 'true' : 'false'}
        >
          <span>
            {item.typed}
            {!item.done && (
              <span
                className="inline-block w-px h-3 ms-0.5 align-middle bg-current animate-pulse"
                aria-hidden
              />
            )}
          </span>
        </Button>
      ))}
    </div>
  );
}
