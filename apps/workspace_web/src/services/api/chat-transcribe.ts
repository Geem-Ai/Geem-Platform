import { apiRequest } from './client';

/**
 * Client-side UX guard. Server ``CHAT_TRANSCRIBE_MAX_MB`` is authoritative.
 * Optional override: ``VITE_CHAT_TRANSCRIBE_MAX_MB``.
 */
const _maxMbRaw = Number(import.meta.env.VITE_CHAT_TRANSCRIBE_MAX_MB);
export const CHAT_TRANSCRIBE_MAX_MB =
  Number.isFinite(_maxMbRaw) && _maxMbRaw > 0 ? _maxMbRaw : 10;
export const CHAT_TRANSCRIBE_MAX_BYTES = CHAT_TRANSCRIBE_MAX_MB * 1024 * 1024;

/** Auto-stop mic recording after this many milliseconds. */
export const CHAT_VOICE_MAX_MS = 60_000;

export type ChatTranscribeResponse = {
  text: string;
  duration_seconds?: number | null;
};

export type TranscribeChatAudioOptions = {
  signal?: AbortSignal;
  /** ISO-639-1 hint from UI locale (e.g. ``en``, ``ar``). */
  language?: string | null;
  /** Filename extension hint for the multipart part (default from blob type). */
  filename?: string;
};

function extensionForBlob(blob: Blob, filename?: string): string {
  if (filename) {
    const dot = filename.lastIndexOf('.');
    if (dot >= 0) return filename.slice(dot + 1).toLowerCase() || 'webm';
  }
  const mime = (blob.type || '').split(';', 1)[0].trim().toLowerCase();
  if (mime.includes('ogg')) return 'ogg';
  if (mime.includes('wav')) return 'wav';
  if (mime.includes('mpeg') || mime.includes('mp3')) return 'mp3';
  if (mime.includes('mp4') || mime.includes('m4a')) return 'm4a';
  return 'webm';
}

/**
 * Upload a mic recording for speech-to-text (Workspace-scoped).
 * Returns editable transcript text for the chat composer.
 */
export async function transcribeChatAudio(
  blob: Blob,
  options: TranscribeChatAudioOptions = {},
): Promise<ChatTranscribeResponse> {
  const ext = extensionForBlob(blob, options.filename);
  const form = new FormData();
  form.append('file', blob, options.filename || `recording.${ext}`);
  const lang = (options.language || '').trim().toLowerCase().slice(0, 2);
  if (lang) {
    form.append('language', lang);
  }
  return apiRequest<ChatTranscribeResponse>('/api/chat/transcribe', {
    method: 'POST',
    body: form,
    signal: options.signal,
  });
}
