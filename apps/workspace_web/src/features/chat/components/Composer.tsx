import { type FormEvent, type KeyboardEvent, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';

interface ComposerProps {
  onSubmit: (question: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
}

export function Composer({ onSubmit, onStop, disabled, isStreaming }: ComposerProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const q = value.trim();
    if (!q || disabled || isStreaming) return;
    onSubmit(q);
    setValue('');
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const q = value.trim();
      if (!q || disabled || isStreaming) return;
      onSubmit(q);
      setValue('');
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 border border-border rounded-lg p-2 bg-background shadow-sm"
    >
      <label className="sr-only" htmlFor="expert-chat-composer">
        {t('chat.placeholder')}
      </label>
      <textarea
        id="expert-chat-composer"
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={t('chat.placeholder')}
        disabled={disabled || isStreaming}
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm placeholder:text-muted-foreground/70 outline-none disabled:opacity-60 max-h-32 overflow-y-auto"
      />
      {isStreaming ? (
        <Button type="button" size="sm" variant="outline" onClick={() => onStop?.()}>
          {t('chat.stop')}
        </Button>
      ) : (
        <Button type="submit" size="sm" disabled={!value.trim() || disabled}>
          {t('chat.send')}
        </Button>
      )}
    </form>
  );
}
