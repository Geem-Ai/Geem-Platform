import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { ChatComposer } from './ChatComposer';

const transcribeChatAudio = vi.fn();

vi.mock('@/services/api', async () => {
  const actual = await vi.importActual<typeof import('@/services/api')>('@/services/api');
  return {
    ...actual,
    transcribeChatAudio: (...args: unknown[]) => transcribeChatAudio(...args),
  };
});

function withI18n(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

class FakeMediaRecorder {
  static isTypeSupported = vi.fn(() => true);
  /** When true, onstop fires on a later macrotask (browser-like). */
  static deferOnStop = true;
  state: 'inactive' | 'recording' = 'inactive';
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;

  constructor(
    _stream: MediaStream,
    options?: { mimeType?: string },
  ) {
    this.mimeType = options?.mimeType || 'audio/webm';
  }

  start() {
    this.state = 'recording';
    this.ondataavailable?.({ data: new Blob(['audio'], { type: this.mimeType }) });
  }

  stop() {
    this.state = 'inactive';
    const fire = () => this.onstop?.(new Event('stop'));
    if (FakeMediaRecorder.deferOnStop) {
      window.setTimeout(fire, 0);
    } else {
      fire();
    }
  }
}

describe('ChatComposer voice recording', () => {
  beforeEach(() => {
    transcribeChatAudio.mockReset();
    FakeMediaRecorder.deferOnStop = true;

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows recording bar, transcribes on send, and fills the input', async () => {
    let resolveTranscribe!: (value: { text: string }) => void;
    transcribeChatAudio.mockImplementation(
      () =>
        new Promise<{ text: string }>((resolve) => {
          resolveTranscribe = resolve;
        }),
    );

    const onValueChange = vi.fn();
    withI18n(
      <ChatComposer onSubmit={vi.fn()} value="" onValueChange={onValueChange} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-button'));
    });
    expect(screen.getByTestId('chat-voice-recording-bar')).toHaveAttribute(
      'data-phase',
      'recording',
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-send'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('chat-voice-transcribing')).toBeInTheDocument();
    });
    expect(transcribeChatAudio).toHaveBeenCalled();

    await act(async () => {
      resolveTranscribe({ text: 'Summarize the key points from my documents.' });
    });

    await waitFor(() => {
      expect(onValueChange).toHaveBeenCalledWith(
        'Summarize the key points from my documents.',
      );
      expect(screen.queryByTestId('chat-voice-recording-bar')).not.toBeInTheDocument();
    });
  });

  it('waits for deferred onstop after Stop before Send (blob race)', async () => {
    transcribeChatAudio.mockResolvedValue({ text: 'after stop' });
    const onValueChange = vi.fn();
    withI18n(
      <ChatComposer onSubmit={vi.fn()} value="" onValueChange={onValueChange} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-button'));
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-stop'));
    });
    expect(screen.getByTestId('chat-voice-recording-bar')).toHaveAttribute(
      'data-phase',
      'stopped',
    );

    // Send immediately while onstop is still pending (setTimeout 0).
    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-send'));
    });

    await waitFor(() => {
      expect(transcribeChatAudio).toHaveBeenCalled();
      expect(onValueChange).toHaveBeenCalledWith('after stop');
    });
  });

  it('cancels recording without filling the input', async () => {
    const onValueChange = vi.fn();
    withI18n(
      <ChatComposer onSubmit={vi.fn()} value="" onValueChange={onValueChange} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-button'));
    });
    fireEvent.click(screen.getByTestId('chat-voice-cancel'));
    expect(screen.queryByTestId('chat-voice-recording-bar')).not.toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
    expect(transcribeChatAudio).not.toHaveBeenCalled();
  });

  it('keeps the stopped bar usable when transcription fails', async () => {
    const { ApiError } = await import('@/services/api');
    transcribeChatAudio.mockRejectedValue(
      new ApiError('quota', { status: 429, code: 'quota_exceeded' }),
    );
    const onValueChange = vi.fn();
    withI18n(
      <ChatComposer onSubmit={vi.fn()} value="" onValueChange={onValueChange} />,
    );

    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-button'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('chat-voice-send'));
    });

    await waitFor(() => {
      expect(transcribeChatAudio).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId('chat-voice-recording-bar')).toHaveAttribute(
        'data-phase',
        'stopped',
      );
    });
    expect(onValueChange).not.toHaveBeenCalled();
  });
});
