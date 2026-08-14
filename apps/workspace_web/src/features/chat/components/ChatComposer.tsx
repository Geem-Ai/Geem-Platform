import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ArrowUp, ChevronDown, Mic, Paperclip, Sparkles, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { Expert } from '@/services/api/types';
import {
  ApiError,
  CHAT_ATTACHMENT_ACCEPT,
  CHAT_ATTACHMENT_MAX_BYTES,
  deleteChatAttachment,
  errorMessageKey,
  uploadChatAttachment,
} from '@/services/api';
import { ExpertPickerDialog } from './ExpertPickerDialog';
import { localizeExpertDisplay } from '@/features/experts/lib/localize';
import {
  VoiceRecordingBar,
  type VoiceRecordingPhase,
} from './VoiceRecordingBar';
import {
  ComposerAttachmentPreview,
  attachmentTypeLabel,
  type ComposerAttachment,
} from './ComposerAttachmentPreview';

const VOICE_TRANSCRIBE_MS = 1600;

interface ChatComposerProps {
  onSubmit: (question: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
  /** Compact footer style vs starter elevated shell. */
  variant?: 'starter' | 'compact';
  /** Optional controlled draft (e.g. sample prompt chips). */
  value?: string;
  onValueChange?: (value: string) => void;
  onFocus?: () => void;
  /** When set, shows Metronic-style Experts picker in the composer toolbar. */
  expertPicker?: {
    experts: Expert[];
    selectedId: string | null;
    onSelect: (expertId: string) => void;
    isLoading?: boolean;
    /** Hide picker on existing conversations (Expert is fixed). */
    disabled?: boolean;
  };
}

export function ChatComposer({
  onSubmit,
  onStop,
  disabled,
  isStreaming,
  placeholder,
  autoFocus,
  className,
  variant = 'compact',
  value: controlledValue,
  onValueChange,
  onFocus,
  expertPicker,
}: ChatComposerProps) {
  const { t } = useTranslation();
  const [uncontrolledValue, setUncontrolledValue] = useState('');
  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : uncontrolledValue;
  const [pickerOpen, setPickerOpen] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoiceRecordingPhase | null>(null);
  const [attachment, setAttachment] = useState<ComposerAttachment | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  /** Ignore the next onFocus from programmatic autoFocus so sample prompts can type. */
  const suppressFocusNotifyRef = useRef(false);
  const transcribeTimerRef = useRef<number | null>(null);
  /** When true, an in-flight upload should delete the server object on completion. */
  const dismissUploadRef = useRef(false);
  /** Server id observed for the current upload (for dismiss-after-commit cleanup). */
  const pendingUploadServerIdRef = useRef<string | null>(null);
  const attachmentRef = useRef<ComposerAttachment | null>(null);

  useEffect(() => {
    attachmentRef.current = attachment;
  }, [attachment]);

  useEffect(() => {
    if (!autoFocus) return;
    const el = textareaRef.current;
    if (!el) return;
    suppressFocusNotifyRef.current = true;
    el.focus({ preventScroll: true });
  }, [autoFocus]);

  useEffect(() => {
    resize();
  }, [value]);

  useEffect(() => {
    return () => {
      if (transcribeTimerRef.current !== null) {
        window.clearTimeout(transcribeTimerRef.current);
      }
      // Prefer completion+delete over abort so we never lose the server id.
      dismissUploadRef.current = true;
    };
  }, []);

  function setValue(next: string) {
    if (!isControlled) setUncontrolledValue(next);
    onValueChange?.(next);
  }

  function resize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function clearTranscribeTimer() {
    if (transcribeTimerRef.current !== null) {
      window.clearTimeout(transcribeTimerRef.current);
      transcribeTimerRef.current = null;
    }
  }

  function cancelVoice() {
    clearTranscribeTimer();
    setVoicePhase(null);
  }

  function startVoice() {
    if (disabled || isStreaming || voicePhase) return;
    clearTranscribeTimer();
    setVoicePhase('recording');
  }

  function stopVoice() {
    if (voicePhase !== 'recording') return;
    setVoicePhase('stopped');
  }

  function beginTranscribe() {
    if (!voicePhase || voicePhase === 'transcribing') return;
    setVoicePhase('transcribing');
    clearTranscribeTimer();
    const existing = value.trim();
    transcribeTimerRef.current = window.setTimeout(() => {
      transcribeTimerRef.current = null;
      const transcript = t('chat.voiceFakeTranscript');
      setValue(existing ? `${existing} ${transcript}` : transcript);
      setVoicePhase(null);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        suppressFocusNotifyRef.current = true;
        el.focus({ preventScroll: true });
        resize();
      });
    }, VOICE_TRANSCRIBE_MS);
  }

  function finishVoice() {
    beginTranscribe();
  }

  async function deleteServerAttachment(serverId: string) {
    try {
      await deleteChatAttachment(serverId);
    } catch (err) {
      if (err instanceof ApiError && (err.code === 'aborted' || err.code === 'chat_attachment_not_found')) {
        return;
      }
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      }
    }
  }

  async function removeAttachment() {
    const current = attachmentRef.current;
    // Do not abort XHR — let it finish so we always learn the server id, then delete.
    dismissUploadRef.current = true;
    setAttachment(null);
    if (fileInputRef.current) fileInputRef.current.value = '';

    const serverId = current?.serverId ?? pendingUploadServerIdRef.current;
    pendingUploadServerIdRef.current = null;
    if (serverId) {
      await deleteServerAttachment(serverId);
    }
  }

  async function startUpload(file: File) {
    await removeAttachment();
    dismissUploadRef.current = false;
    pendingUploadServerIdRef.current = null;

    if (file.size > CHAT_ATTACHMENT_MAX_BYTES) {
      toast.error(t('chat.attachmentTooLarge'));
      return;
    }

    const localId = `local-${Date.now()}`;
    const draft: ComposerAttachment = {
      id: localId,
      serverId: null,
      name: file.name,
      typeLabel: attachmentTypeLabel(file.name),
      progress: 0,
    };
    setAttachment(draft);

    try {
      const uploaded = await uploadChatAttachment(file, {
        onProgress: (percent) => {
          setAttachment((prev) =>
            prev && prev.id === localId ? { ...prev, progress: percent } : prev,
          );
        },
      });
      pendingUploadServerIdRef.current = uploaded.id;

      if (dismissUploadRef.current) {
        pendingUploadServerIdRef.current = null;
        void deleteServerAttachment(uploaded.id);
        return;
      }

      setAttachment({
        id: localId,
        serverId: uploaded.id,
        name: uploaded.original_filename || file.name,
        typeLabel: attachmentTypeLabel(uploaded.original_filename || file.name),
        progress: 100,
      });
      pendingUploadServerIdRef.current = null;
    } catch (err) {
      const orphanId = pendingUploadServerIdRef.current;
      pendingUploadServerIdRef.current = null;
      if (orphanId || dismissUploadRef.current) {
        if (orphanId) void deleteServerAttachment(orphanId);
        return;
      }
      setAttachment(null);
      if (err instanceof ApiError && err.code === 'upload_too_large') {
        toast.error(t('chat.attachmentTooLarge'));
        return;
      }
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
        return;
      }
      toast.error(t('chat.attachmentUploadFailed'));
    }
  }

  function openFilePicker() {
    if (disabled || isStreaming || voicePhase) return;
    fileInputRef.current?.click();
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Allow re-selecting the same file later.
    e.target.value = '';
    if (!file) return;
    void startUpload(file);
  }

  function submit() {
    const q = value.trim();
    const attachmentUploading = Boolean(
      attachment && (!attachment.serverId || attachment.progress < 100),
    );
    if (!q || disabled || isStreaming || voicePhase || attachmentUploading) return;
    // Keep ready attachment in the composer for a later chat-turn wiring.
    onSubmit(q);
    setValue('');
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        suppressFocusNotifyRef.current = true;
        textareaRef.current.style.height = 'auto';
        textareaRef.current.focus({ preventScroll: true });
      }
    });
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    submit();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  const attachmentUploading = Boolean(
    attachment && (!attachment.serverId || attachment.progress < 100),
  );
  const canSend =
    Boolean(value.trim()) &&
    !disabled &&
    !isStreaming &&
    !voicePhase &&
    !attachmentUploading;
  const selectedExpert = expertPicker?.selectedId
    ? expertPicker.experts.find((e) => e.id === expertPicker.selectedId)
    : null;
  const selectedLabel = selectedExpert
    ? localizeExpertDisplay(selectedExpert, t).name
    : null;

  return (
    <>
      <form
        onSubmit={handleSubmit}
        className={cn(
          'relative flex flex-col gap-2 transition-all',
          voicePhase
            ? 'bg-transparent border-0 shadow-none p-0'
            : cn(
                'bg-background',
                variant === 'starter'
                  ? 'rounded-2xl border shadow-lg p-4'
                  : 'rounded-2xl border shadow-md p-3',
              ),
          className,
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={CHAT_ATTACHMENT_ACCEPT}
          className="sr-only"
          tabIndex={-1}
          data-testid="chat-attach-input"
          onChange={handleFileChange}
        />

        {voicePhase ? (
          <VoiceRecordingBar
            phase={voicePhase}
            onCancel={cancelVoice}
            onStop={stopVoice}
            onSend={finishVoice}
          />
        ) : (
          <>
            {attachment && (
              <div className="px-1 pt-0.5">
                <ComposerAttachmentPreview
                  attachment={attachment}
                  onRemove={removeAttachment}
                />
              </div>
            )}

            <label className="sr-only" htmlFor="geem-chat-composer">
              {placeholder ?? t('chat.placeholder')}
            </label>
            <textarea
              id="geem-chat-composer"
              ref={textareaRef}
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                resize();
              }}
              onFocus={() => {
                if (suppressFocusNotifyRef.current) {
                  suppressFocusNotifyRef.current = false;
                  return;
                }
                onFocus?.();
              }}
              onKeyDown={handleKeyDown}
              placeholder={placeholder ?? t('chat.placeholder')}
              disabled={disabled && !expertPicker}
              rows={1}
              className="w-full resize-none bg-transparent text-sm placeholder:text-muted-foreground/70 outline-none disabled:opacity-60 max-h-40 overflow-y-auto px-1 py-2"
            />
            <div className="flex items-center justify-between gap-2 mt-1">
              <div className="flex items-center gap-1.5 min-w-0">
                {expertPicker && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={expertPicker.disabled || isStreaming}
                    onClick={() => setPickerOpen(true)}
                    className="h-8 px-3 rounded-lg bg-muted/50 hover:bg-muted text-xs font-medium gap-1.5 border-0 max-w-[14rem]"
                    data-testid="experts-picker-button"
                  >
                    <Sparkles className="size-3.5 shrink-0" />
                    <span className="truncate">
                      {selectedLabel ?? t('chat.expertsButton')}
                    </span>
                    <ChevronDown className="size-3 opacity-50 shrink-0" />
                  </Button>
                )}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 rounded-lg text-muted-foreground hover:text-foreground"
                      aria-label={t('chat.attach')}
                      data-testid="chat-attach-button"
                      disabled={disabled || isStreaming}
                      onClick={openFilePicker}
                    >
                      <Paperclip className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">{t('chat.attach')}</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 rounded-lg text-muted-foreground hover:text-foreground"
                      aria-label={t('chat.voice')}
                      data-testid="chat-voice-button"
                      disabled={disabled || isStreaming}
                      onClick={startVoice}
                    >
                      <Mic className="size-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top">{t('chat.voice')}</TooltipContent>
                </Tooltip>
              </div>

              {isStreaming ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="rounded-xl gap-1.5 shrink-0"
                  onClick={() => onStop?.()}
                >
                  <Square className="size-3.5 fill-current" />
                  {t('chat.stopGenerating')}
                </Button>
              ) : (
                <Button
                  type="submit"
                  size="icon"
                  variant={canSend ? 'primary' : 'secondary'}
                  disabled={!canSend}
                  className={cn('size-9 rounded-xl shrink-0', !canSend && 'opacity-50')}
                  aria-label={t('chat.send')}
                >
                  <ArrowUp className="size-4" />
                </Button>
              )}
            </div>
          </>
        )}
      </form>

      {expertPicker && (
        <ExpertPickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          experts={expertPicker.experts}
          selectedId={expertPicker.selectedId}
          onSelect={expertPicker.onSelect}
          isLoading={expertPicker.isLoading}
        />
      )}
    </>
  );
}

/** @deprecated Prefer ChatComposer — kept for any residual imports. */
export { ChatComposer as Composer };
