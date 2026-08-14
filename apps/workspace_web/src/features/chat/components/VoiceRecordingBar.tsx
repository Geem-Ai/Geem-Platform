import { useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUp, Loader2, Square, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export type VoiceRecordingPhase = 'recording' | 'stopped' | 'transcribing';

interface VoiceRecordingBarProps {
  phase: VoiceRecordingPhase;
  onCancel: () => void;
  onStop: () => void;
  onSend: () => void;
  className?: string;
}

const BAR_COUNT = 48;

/** Deterministic base heights so SSR/tests stay stable; animated via CSS. */
function buildBaseHeights(count: number): number[] {
  const heights: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const wave = Math.sin(i * 0.45) * 0.35 + Math.sin(i * 0.17) * 0.25;
    heights.push(0.28 + ((wave + 1) / 2) * 0.72);
  }
  return heights;
}

function Waveform({ active }: { active: boolean }) {
  const heights = useMemo(() => buildBaseHeights(BAR_COUNT), []);

  return (
    <div
      className="flex flex-1 items-center justify-center gap-[2px] h-8 min-w-0 overflow-hidden px-1"
      aria-hidden
    >
      {heights.map((h, i) => (
        <span
          key={i}
          className={cn(
            'w-[2px] rounded-full bg-zinc-400/80',
            active ? 'animate-voice-bar' : 'opacity-55',
          )}
          style={{
            height: `${Math.round(h * 100)}%`,
            animationDelay: active ? `${(i % 12) * -0.08}s` : undefined,
          }}
        />
      ))}
    </div>
  );
}

function CircleIconButton({
  label,
  onClick,
  disabled,
  className,
  children,
  testId,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      data-testid={testId}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'inline-flex size-9 shrink-0 items-center justify-center rounded-full transition-opacity',
        'disabled:pointer-events-none disabled:opacity-40',
        className,
      )}
    >
      {children}
    </button>
  );
}

export function VoiceRecordingBar({
  phase,
  onCancel,
  onStop,
  onSend,
  className,
}: VoiceRecordingBarProps) {
  const { t } = useTranslation();
  const isTranscribing = phase === 'transcribing';
  const isRecording = phase === 'recording';

  return (
    <div
      role="group"
      aria-label={t('chat.voiceRecording')}
      data-testid="chat-voice-recording-bar"
      data-phase={phase}
      className={cn(
        'flex w-full items-center gap-2 rounded-full px-2 py-1.5',
        'bg-zinc-900 text-zinc-100 shadow-md',
        'dark:bg-zinc-950',
        className,
      )}
    >
      <CircleIconButton
        label={t('chat.cancel')}
        onClick={onCancel}
        disabled={isTranscribing}
        testId="chat-voice-cancel"
        className="bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
      >
        <X className="size-4" strokeWidth={2} />
      </CircleIconButton>

      <div className="hidden sm:flex items-center gap-1 px-0.5" aria-hidden>
        {Array.from({ length: 6 }).map((_, i) => (
          <span key={i} className="size-1 rounded-full bg-zinc-600" />
        ))}
      </div>

      {isTranscribing ? (
        <div
          className="flex flex-1 items-center justify-center gap-2 min-w-0 px-2 py-1"
          data-testid="chat-voice-transcribing"
        >
          <Loader2 className="size-4 shrink-0 animate-spin text-zinc-300" />
          <span className="text-sm font-medium text-zinc-200 truncate">
            {t('chat.transcribing')}
          </span>
        </div>
      ) : (
        <Waveform active={isRecording} />
      )}

      {!isTranscribing && (
        <CircleIconButton
          label={t('chat.stopRecording')}
          onClick={onStop}
          disabled={!isRecording}
          testId="chat-voice-stop"
          className="bg-zinc-800 text-zinc-100 hover:bg-zinc-700 disabled:opacity-30"
        >
          <Square className="size-3.5 fill-current" />
        </CircleIconButton>
      )}

      <CircleIconButton
        label={t('chat.send')}
        onClick={onSend}
        disabled={isTranscribing}
        testId="chat-voice-send"
        className="bg-white text-zinc-900 hover:bg-zinc-100 shadow-sm"
      >
        <ArrowUp className="size-4" strokeWidth={2.5} />
      </CircleIconButton>
    </div>
  );
}
