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
import { ArrowUp, ChevronDown, FileText, ImageIcon, Mic, Paperclip, Sparkles, Square, Type } from 'lucide-react';
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
  CHAT_ATTACHMENT_ACCEPT_BY_KIND,
  CHAT_ATTACHMENT_MAX_BYTES,
  CHAT_TRANSCRIBE_MAX_BYTES,
  CHAT_VOICE_MAX_MS,
  deleteChatAttachment,
  errorMessageKey,
  transcribeChatAudio,
  uploadChatAttachment,
  type ChatAttachmentKind,
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

export type ChatComposerSubmitOptions = {
  attachmentId?: string;
  attachmentMeta?: {
    filename: string;
    mimeType: string;
    byteSize?: number;
  };
};

function pickRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return undefined;
  }
  for (const type of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg']) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return undefined;
}

interface ChatComposerProps {
  onSubmit: (question: string, options?: ChatComposerSubmitOptions) => void;
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
  const { t, i18n } = useTranslation();
  const [uncontrolledValue, setUncontrolledValue] = useState('');
  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : uncontrolledValue;
  const [pickerOpen, setPickerOpen] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoiceRecordingPhase | null>(null);
  const [attachment, setAttachment] = useState<ComposerAttachment | null>(null);
  const [fileAccept, setFileAccept] = useState(
    CHAT_ATTACHMENT_ACCEPT_BY_KIND.pdf,
  );
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachMenuRef = useRef<HTMLDivElement>(null);
  /** Ignore the next onFocus from programmatic autoFocus so sample prompts can type. */
  const suppressFocusNotifyRef = useRef(false);
  /** When true, an in-flight upload should delete the server object on completion. */
  const dismissUploadRef = useRef(false);
  /** Server id observed for the current upload (for dismiss-after-commit cleanup). */
  const pendingUploadServerIdRef = useRef<string | null>(null);
  const attachmentRef = useRef<ComposerAttachment | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const audioBlobRef = useRef<Blob | null>(null);
  const voiceMaxTimerRef = useRef<number | null>(null);
  const voicePhaseRef = useRef<VoiceRecordingPhase | null>(null);
  const transcribeAbortRef = useRef<AbortController | null>(null);
  /** Blocks double-tap while getUserMedia / recorder setup is in flight. */
  const voiceStartingRef = useRef(false);
  /** Shared stop promise so Stop → Send waits for MediaRecorder.onstop blob. */
  const recorderStopPromiseRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    attachmentRef.current = attachment;
  }, [attachment]);

  useEffect(() => {
    voicePhaseRef.current = voicePhase;
  }, [voicePhase]);

  useEffect(() => {
    if (!attachMenuOpen) return;
    function onDocPointerDown(event: MouseEvent) {
      const root = attachMenuRef.current;
      if (root && !root.contains(event.target as Node)) {
        setAttachMenuOpen(false);
      }
    }
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') setAttachMenuOpen(false);
    }
    document.addEventListener('mousedown', onDocPointerDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [attachMenuOpen]);

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
      dismissUploadRef.current = true;
      clearVoiceMaxTimer();
      transcribeAbortRef.current?.abort();
      stopMediaTracks();
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

  function clearVoiceMaxTimer() {
    if (voiceMaxTimerRef.current !== null) {
      window.clearTimeout(voiceMaxTimerRef.current);
      voiceMaxTimerRef.current = null;
    }
  }

  function stopMediaTracks() {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop();
      } catch {
        /* ignore */
      }
    }
    mediaRecorderRef.current = null;
    const stream = mediaStreamRef.current;
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
    }
    mediaStreamRef.current = null;
  }

  function discardVoiceCapture() {
    clearVoiceMaxTimer();
    stopMediaTracks();
    audioChunksRef.current = [];
    audioBlobRef.current = null;
    recorderStopPromiseRef.current = null;
  }

  function focusComposerInput() {
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      suppressFocusNotifyRef.current = true;
      el.focus({ preventScroll: true });
      resize();
    });
  }

  /** Stop the recorder once and resolve after onstop has written audioBlobRef. */
  function stopRecorderAndAwaitBlob(): Promise<void> {
    if (recorderStopPromiseRef.current) {
      return recorderStopPromiseRef.current;
    }
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      return Promise.resolve();
    }
    recorderStopPromiseRef.current = new Promise<void>((resolve) => {
      const prev = recorder.onstop;
      recorder.onstop = (event) => {
        try {
          if (typeof prev === 'function') {
            prev.call(recorder, event);
          }
        } finally {
          resolve();
        }
      };
      try {
        recorder.stop();
      } catch {
        resolve();
      }
    });
    return recorderStopPromiseRef.current;
  }

  function cancelVoice() {
    transcribeAbortRef.current?.abort();
    transcribeAbortRef.current = null;
    discardVoiceCapture();
    setVoicePhase(null);
  }

  async function startVoice() {
    if (disabled || isStreaming || voicePhase || voiceStartingRef.current) return;
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      toast.error(t('chat.voiceUnsupported'));
      return;
    }
    if (typeof MediaRecorder === 'undefined') {
      toast.error(t('chat.voiceUnsupported'));
      return;
    }

    voiceStartingRef.current = true;
    discardVoiceCapture();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const mimeType = pickRecorderMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      audioBlobRef.current = null;
      recorderStopPromiseRef.current = null;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const type = recorder.mimeType || mimeType || 'audio/webm';
        const blob = new Blob(audioChunksRef.current, { type });
        audioChunksRef.current = [];
        audioBlobRef.current = blob.size > 0 ? blob : null;
        const streamTracks = mediaStreamRef.current;
        if (streamTracks) {
          for (const track of streamTracks.getTracks()) {
            track.stop();
          }
          mediaStreamRef.current = null;
        }
      };

      recorder.start(250);
      setVoicePhase('recording');
      clearVoiceMaxTimer();
      voiceMaxTimerRef.current = window.setTimeout(() => {
        voiceMaxTimerRef.current = null;
        if (voicePhaseRef.current === 'recording') {
          toast.message(t('chat.voiceMaxDuration'));
          stopVoice();
        }
      }, CHAT_VOICE_MAX_MS);
    } catch (err) {
      discardVoiceCapture();
      setVoicePhase(null);
      const name = err instanceof DOMException ? err.name : '';
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        toast.error(t('chat.voicePermissionDenied'));
        return;
      }
      toast.error(t('chat.voiceStartFailed'));
    } finally {
      voiceStartingRef.current = false;
    }
  }

  function stopVoice() {
    if (voicePhaseRef.current !== 'recording') return;
    clearVoiceMaxTimer();
    void stopRecorderAndAwaitBlob();
    setVoicePhase('stopped');
  }

  async function beginTranscribe() {
    if (!voicePhaseRef.current || voicePhaseRef.current === 'transcribing') return;
    clearVoiceMaxTimer();
    // Always await stop completion — Stop → Send must not race onstop.
    await stopRecorderAndAwaitBlob();
    if (!voicePhaseRef.current) {
      // Cancelled while waiting for the final audio chunk.
      return;
    }

    const blob = audioBlobRef.current;
    if (!blob || blob.size === 0) {
      discardVoiceCapture();
      setVoicePhase(null);
      toast.error(t('chat.voiceEmptyRecording'));
      return;
    }
    if (blob.size > CHAT_TRANSCRIBE_MAX_BYTES) {
      discardVoiceCapture();
      setVoicePhase(null);
      toast.error(t('chat.voiceTooLarge'));
      return;
    }

    setVoicePhase('transcribing');
    const existing = value.trim();
    const abort = new AbortController();
    transcribeAbortRef.current = abort;
    try {
      const result = await transcribeChatAudio(blob, {
        signal: abort.signal,
        language: i18n.language,
      });
      if (!voicePhaseRef.current) return;
      const transcript = (result.text || '').trim();
      if (!transcript) {
        toast.error(t('chat.voiceTranscribeFailed'));
        setVoicePhase('stopped');
        return;
      }
      setValue(existing ? `${existing} ${transcript}` : transcript);
      discardVoiceCapture();
      setVoicePhase(null);
      focusComposerInput();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'aborted') {
        return;
      }
      if (!voicePhaseRef.current) return;
      if (err instanceof ApiError) {
        toast.error(t(errorMessageKey(err.code)));
      } else {
        toast.error(t('chat.voiceTranscribeFailed'));
      }
      // Keep blob so the user can retry Send from the stopped bar.
      setVoicePhase('stopped');
    } finally {
      if (transcribeAbortRef.current === abort) {
        transcribeAbortRef.current = null;
      }
    }
  }

  function finishVoice() {
    void beginTranscribe();
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
      mimeType: file.type || undefined,
      byteSize: file.size,
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
        mimeType: uploaded.mime_type,
        byteSize: uploaded.byte_size,
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

  function openFilePicker(kind: ChatAttachmentKind) {
    if (disabled || isStreaming || voicePhase) return;
    setAttachMenuOpen(false);
    setFileAccept(CHAT_ATTACHMENT_ACCEPT_BY_KIND[kind]);
    // Defer click so accept attribute is applied before the dialog opens.
    requestAnimationFrame(() => {
      fileInputRef.current?.click();
    });
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
    const attachmentReady = Boolean(attachment?.serverId && attachment.progress >= 100);
    if (
      (!q && !attachmentReady) ||
      disabled ||
      isStreaming ||
      voicePhase ||
      attachmentUploading
    ) {
      return;
    }
    const opts: ChatComposerSubmitOptions | undefined = attachmentReady
      ? {
          attachmentId: attachment!.serverId!,
          attachmentMeta: {
            filename: attachment!.name,
            mimeType: attachment!.mimeType || 'application/octet-stream',
            byteSize: attachment!.byteSize,
          },
        }
      : undefined;
    onSubmit(q, opts);
    setValue('');
    setAttachment(null);
    pendingUploadServerIdRef.current = null;
    if (fileInputRef.current) fileInputRef.current.value = '';
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
  const attachmentReady = Boolean(attachment?.serverId && attachment.progress >= 100);
  const canSend =
    (Boolean(value.trim()) || attachmentReady) &&
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
          accept={fileAccept}
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
                <div className="relative" ref={attachMenuRef}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="size-8 rounded-full text-muted-foreground hover:text-foreground hover:bg-muted"
                        aria-label={t('chat.attach')}
                        aria-expanded={attachMenuOpen}
                        aria-haspopup="menu"
                        data-testid="chat-attach-button"
                        disabled={disabled || isStreaming || Boolean(voicePhase)}
                        onClick={() => setAttachMenuOpen((open) => !open)}
                      >
                        <Paperclip className="size-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top">{t('chat.attach')}</TooltipContent>
                  </Tooltip>
                  {attachMenuOpen ? (
                    <div
                      role="menu"
                      data-testid="chat-attach-menu"
                      className="absolute top-full start-0 z-50 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg"
                    >
                      <button
                        type="button"
                        role="menuitem"
                        data-testid="chat-attach-images"
                        className="flex w-full cursor-pointer select-none items-center gap-3 rounded-xl px-3 py-2.5 text-start outline-hidden transition-colors hover:bg-accent"
                        onClick={() => openFilePicker('images')}
                      >
                        <ImageIcon className="size-4 shrink-0 text-foreground" aria-hidden />
                        <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
                          <span className="text-sm font-medium text-foreground">
                            {t('chat.attachImages')}
                          </span>
                          <span className="truncate text-xs text-muted-foreground">
                            {t('chat.attachImagesHint')}
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        data-testid="chat-attach-pdf"
                        className="flex w-full cursor-pointer select-none items-center gap-3 rounded-xl px-3 py-2.5 text-start outline-hidden transition-colors hover:bg-accent"
                        onClick={() => openFilePicker('pdf')}
                      >
                        <FileText className="size-4 shrink-0 text-foreground" aria-hidden />
                        <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
                          <span className="text-sm font-medium text-foreground">
                            {t('chat.attachPdf')}
                          </span>
                          <span className="truncate text-xs text-muted-foreground">
                            {t('chat.attachPdfHint')}
                          </span>
                        </span>
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        data-testid="chat-attach-text"
                        className="flex w-full cursor-pointer select-none items-center gap-3 rounded-xl px-3 py-2.5 text-start outline-hidden transition-colors hover:bg-accent"
                        onClick={() => openFilePicker('text')}
                      >
                        <Type className="size-4 shrink-0 text-foreground" aria-hidden />
                        <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
                          <span className="text-sm font-medium text-foreground">
                            {t('chat.attachText')}
                          </span>
                          <span className="truncate text-xs text-muted-foreground">
                            {t('chat.attachTextHint')}
                          </span>
                        </span>
                      </button>
                    </div>
                  ) : null}
                </div>
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
                      onClick={() => void startVoice()}
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
