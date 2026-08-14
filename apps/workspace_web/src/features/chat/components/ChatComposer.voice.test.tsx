import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';
import i18n from '@/lib/i18n';
import { ChatComposer } from './ChatComposer';

function withI18n(ui: React.ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

describe('ChatComposer voice recording', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows recording bar, transcribes on send, and fills the input', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const onValueChange = vi.fn();
    withI18n(
      <ChatComposer onSubmit={vi.fn()} value="" onValueChange={onValueChange} />,
    );

    fireEvent.click(screen.getByTestId('chat-voice-button'));
    expect(screen.getByTestId('chat-voice-recording-bar')).toHaveAttribute(
      'data-phase',
      'recording',
    );

    fireEvent.click(screen.getByTestId('chat-voice-send'));
    expect(screen.getByTestId('chat-voice-transcribing')).toBeInTheDocument();
    expect(screen.getByText(/Transcribing/i)).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1600);
    });

    expect(screen.queryByTestId('chat-voice-recording-bar')).not.toBeInTheDocument();
    expect(onValueChange).toHaveBeenCalledWith(
      'Summarize the key points from my documents.',
    );
  });

  it('cancels recording without filling the input', () => {
    const onValueChange = vi.fn();
    withI18n(
      <ChatComposer onSubmit={vi.fn()} value="" onValueChange={onValueChange} />,
    );

    fireEvent.click(screen.getByTestId('chat-voice-button'));
    fireEvent.click(screen.getByTestId('chat-voice-cancel'));
    expect(screen.queryByTestId('chat-voice-recording-bar')).not.toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
  });
});
