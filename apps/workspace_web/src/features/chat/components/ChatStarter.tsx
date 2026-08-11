import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { geemAvatarUrl } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import type { Expert } from '@/services/api/types';
import { localizeExpertDisplay } from '@/features/experts/lib/localize';
import { ChatComposer } from './ChatComposer';
import { SamplePromptSuggestions } from './SamplePromptSuggestions';

interface ChatStarterProps {
  experts: Expert[];
  selectedExpertId: string | null;
  onSelectExpert: (expertId: string) => void;
  onSubmit: (content: string) => void;
  expertsLoading?: boolean;
  submitting?: boolean;
  disabled?: boolean;
  askHint?: string | null;
  invalidDeepLink?: boolean;
  className?: string;
}

export function ChatStarter({
  experts,
  selectedExpertId,
  onSelectExpert,
  onSubmit,
  expertsLoading,
  submitting,
  disabled,
  askHint,
  invalidDeepLink,
  className,
}: ChatStarterProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState('');
  const [promptsPaused, setPromptsPaused] = useState(false);
  const selected = selectedExpertId
    ? experts.find((e) => e.id === selectedExpertId)
    : null;
  const selectedName = selected ? localizeExpertDisplay(selected, t).name : null;

  function pausePrompts() {
    setPromptsPaused(true);
  }

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center flex-1 p-6',
        className,
      )}
      data-testid="chat-starter"
    >
      <div className="w-full max-w-3xl flex flex-col items-center">
        <div className="flex flex-col items-center gap-6 mb-8 text-center">
          <div className="size-16 rounded-2xl bg-primary/10 flex items-center justify-center overflow-hidden">
            <img
              src={geemAvatarUrl()}
              alt={t('app.name')}
              className="size-12 object-contain"
            />
          </div>
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">
              {t('chat.starterTitle')}
            </h1>
            <p className="text-muted-foreground text-lg">{t('chat.starterSubtitle')}</p>
          </div>
        </div>

        {invalidDeepLink && (
          <p className="text-sm text-destructive mb-4" role="alert">
            {t('chat.expertNotFoundHint')}
          </p>
        )}

        <div className="w-full">
          {askHint && (
            <p className="text-xs text-muted-foreground mb-2 text-center">{askHint}</p>
          )}
          <ChatComposer
            variant="starter"
            onSubmit={(content) => {
              pausePrompts();
              onSubmit(content);
            }}
            disabled={disabled || !selected || submitting}
            isStreaming={submitting}
            value={draft}
            onValueChange={(next) => {
              setDraft(next);
              if (next.length > 0) pausePrompts();
            }}
            onFocus={pausePrompts}
            placeholder={
              selectedName
                ? t('chat.askHint', { name: selectedName })
                : t('chat.placeholderSelectExpert')
            }
            autoFocus={Boolean(selected)}
            expertPicker={{
              experts,
              selectedId: selectedExpertId,
              onSelect: onSelectExpert,
              isLoading: expertsLoading,
            }}
          />
          {!selected && !expertsLoading && (
            <p className="text-xs text-muted-foreground text-center mt-3">
              {t('chat.expertRequired')}
            </p>
          )}

          <SamplePromptSuggestions
            paused={promptsPaused}
            onSelect={(prompt) => {
              pausePrompts();
              setDraft(prompt);
              if (!selected || disabled || submitting) return;
              onSubmit(prompt);
            }}
          />
        </div>

        <p className="text-xs text-muted-foreground text-center mt-8 max-w-md">
          {t('chat.starterDisclaimer')}
        </p>
      </div>
    </div>
  );
}
